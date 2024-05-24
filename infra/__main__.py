import pulumi
import pulumi_aws as aws
import pulumi_docker as docker

env = pulumi.get_stack()

SERVICE_NAME = "graphql-websocket"

# API & stage

websocket_api = aws.apigatewayv2.Api(
    resource_name=SERVICE_NAME,
    name=f"{SERVICE_NAME}-{env}",
    protocol_type="WEBSOCKET",
    route_selection_expression="$request.body.action",
)

stage = aws.apigatewayv2.Stage(
    resource_name=SERVICE_NAME,
    api_id=websocket_api.id,
    name=env,
    # default_route_settings=aws.apigatewayv2.StageDefaultRouteSettingsArgs(
    #     data_trace_enabled=True,
    #     detailed_metrics_enabled=True,
    #     logging_level="INFO",
    #     throttling_burst_limit=5000,
    #     throttling_rate_limit=10000,
    # ),
    opts=pulumi.ResourceOptions(parent=websocket_api),
)

# Docker image

repo = aws.ecr.Repository(
    resource_name=SERVICE_NAME,
    name=f"test-{env}",
    force_delete=True,
)

auth = aws.ecr.get_authorization_token()

image = docker.Image(
    resource_name=SERVICE_NAME,
    image_name=repo.repository_url.apply(lambda url: f"{url}:{SERVICE_NAME}"),
    build=docker.DockerBuildArgs(context="../", platform="linux/arm64"),
    registry=docker.RegistryArgs(
        server=auth.proxy_endpoint,
        username=auth.user_name,
        password=auth.password,
    ),
    opts=pulumi.ResourceOptions(parent=repo),
)

# Websocket function

websocket_role = aws.iam.Role(
    resource_name="websocket",
    assume_role_policy=aws.iam.get_policy_document(
        statements=[
            aws.iam.GetPolicyDocumentStatementArgs(
                actions=["sts:AssumeRole"],
                effect="Allow",
                principals=[
                    aws.iam.GetPolicyDocumentStatementPrincipalArgs(
                        identifiers=["lambda.amazonaws.com"],
                        type="Service",
                    )
                ],
            )
        ]
    ).json,
    inline_policies=[
        aws.iam.RoleInlinePolicyArgs(
            name="PolicyExecuteApiManageConnections",
            policy=aws.iam.get_policy_document(
                statements=[
                    aws.iam.GetPolicyDocumentStatementArgs(
                        actions=["execute-api:ManageConnections"],
                        effect="Allow",
                        resources=[
                            websocket_api.execution_arn.apply(
                                lambda execution_arn: f"{execution_arn}/*"
                            ),
                        ],
                    )
                ]
            ).json,
        )
    ],
)

websocket_function = aws.lambda_.Function(
    resource_name="websocket",
    package_type="Image",
    image_uri=image.repo_digest,
    image_config=aws.lambda_.FunctionImageConfigArgs(
        commands=["api.websocket_function.lambda_handler"],
    ),
    memory_size=256,
    environment=aws.lambda_.FunctionEnvironmentArgs(
        variables={
            "POWERTOOLS_SERVICE_NAME": "websocket",
            "POWERTOOLS_LOGGER_LOG_EVENT": "1",
            "WEBSOCKET_CONNECTION_URL": stage.invoke_url.apply(
                lambda websocket_url: websocket_url.replace("wss://", "https://")
            ),
        }
    ),
    role=websocket_role.arn,
    opts=pulumi.ResourceOptions(parent=image),
)

# Websocket API permission to invoke the lambda function

aws.lambda_.Permission(
    resource_name="graphql-websocket",
    action="lambda:InvokeFunction",
    function=websocket_function.name,
    principal="apigateway.amazonaws.com",
    source_arn=websocket_api.execution_arn.apply(
        lambda execution_arn: f"{execution_arn}/*"
    ),
    opts=pulumi.ResourceOptions(parent=websocket_api),
)

# Websocket API integration, routes & deployment

integration = aws.apigatewayv2.Integration(
    resource_name="websocket",
    api_id=websocket_api.id,
    integration_type="AWS_PROXY",
    connection_type="INTERNET",
    content_handling_strategy="CONVERT_TO_TEXT",
    integration_method="POST",
    integration_uri=websocket_function.invoke_arn,
    passthrough_behavior="WHEN_NO_MATCH",
    opts=pulumi.ResourceOptions(parent=websocket_api),
)

routes = [
    aws.apigatewayv2.Route(
        resource_name=f"websocket-{route}",
        api_id=websocket_api.id,
        route_key=route,
        authorization_type="NONE",
        target=integration.id.apply(
            lambda integration_id: f"integrations/{integration_id}"
        ),
        opts=pulumi.ResourceOptions(parent=integration),
    )
    for route in ["$connect", "$disconnect", "$default"]
]

deployment = aws.apigatewayv2.Deployment(
    resource_name="websocket",
    api_id=websocket_api.id,
    description="Deployed via Pulumi",
    opts=pulumi.ResourceOptions(depends_on=routes, parent=websocket_api),
)

# GraphQL Function

graphql_role = aws.iam.Role(
    resource_name="graphql",
    assume_role_policy=aws.iam.get_policy_document(
        statements=[
            aws.iam.GetPolicyDocumentStatementArgs(
                actions=["sts:AssumeRole"],
                effect="Allow",
                principals=[
                    aws.iam.GetPolicyDocumentStatementPrincipalArgs(
                        identifiers=["lambda.amazonaws.com"],
                        type="Service",
                    )
                ],
            )
        ]
    ).json,
)

graphql_function = aws.lambda_.Function(
    resource_name="graphql",
    package_type="Image",
    image_uri=image.repo_digest,
    image_config=aws.lambda_.FunctionImageConfigArgs(
        commands=["api.graphql_function.lambda_handler"],
    ),
    memory_size=256,
    environment=aws.lambda_.FunctionEnvironmentArgs(
        variables={
            "POWERTOOLS_SERVICE_NAME": "graphql",
            "POWERTOOLS_LOGGER_LOG_EVENT": "1",
            "WEBSOCKET_ENDPOINT": (
                stage.invoke_url
            ),  # Websocket endpoint is required to render the GraphiQL interface
        }
    ),
    role=graphql_role.arn,
    opts=pulumi.ResourceOptions(parent=image, depends_on=[websocket_function]),
)

graphql_url = aws.lambda_.FunctionUrl(
    resource_name="graphql",
    function_name=graphql_function.name,
    authorization_type="NONE",
    opts=pulumi.ResourceOptions(parent=graphql_function),
)

# Exports

pulumi.export("graphql:endpoint", graphql_url.function_url)
pulumi.export("graphql:websocket_endpoint", stage.invoke_url)
