from __future__ import annotations

import json
import os

import boto3
from aws_lambda_powertools.logging import Logger
from aws_lambda_powertools.tracing import Tracer
from aws_lambda_powertools.utilities.data_classes import (
    APIGatewayProxyEvent,
    event_source,
)
from aws_lambda_powertools.utilities.typing import LambdaContext

# https://github.com/strawberry-graphql/strawberry/blob/main/strawberry/subscriptions/protocols/graphql_ws/__init__.py
# https://github.com/strawberry-graphql/strawberry/blob/main/strawberry/subscriptions/protocols/graphql_transport_ws/types.py
# TODO: use graphql_transport_ws
from strawberry.subscriptions.protocols.graphql_ws import GQL_CONNECTION_ACK, GQL_DATA

tracer = Tracer()
logger = Logger()

client = boto3.client(
    "apigatewaymanagementapi", endpoint_url=os.environ["WEBSOCKET_CONNECTION_URL"]
)


@tracer.capture_lambda_handler(capture_response=True)  # type: ignore
@logger.inject_lambda_context(log_event=True)
@event_source(data_class=APIGatewayProxyEvent)
def lambda_handler(event: APIGatewayProxyEvent, context: LambdaContext) -> dict | None:
    if not event.request_context.route_key:
        raise ValueError("Route key is not defined")

    if not event.request_context.connection_id:
        raise ValueError("Connection ID is not defined")

    if event.request_context.route_key in ["$connect", "$disconnect"]:
        return {
            "statusCode": 200,
            "headers": {
                # TODO: upgrade to graphql_transport_ws
                "Sec-WebSocket-Protocol": "graphql-ws",
            },
        }

    elif event.request_context.route_key == "$default":
        # Inspired from:
        # https://github.com/patrick91/strawberry-lambda-ws/blob/main/app.py

        client.post_to_connection(
            ConnectionId=event.request_context.connection_id,
            Data=json.dumps({"type": GQL_CONNECTION_ACK}),
        )
        client.post_to_connection(
            ConnectionId=event.request_context.connection_id,
            Data=json.dumps(
                {"type": GQL_DATA, "payload": {"data": "example"}, "id": "1"}
            ),
        )

        # The Lambda needs to explicitely return a 200, otherwise the websocket API
        # will consider it malformed response
        return {"statusCode": 200}

    else:
        raise ValueError(f"Unsupported route key: {event.request_context.route_key}")
