from __future__ import annotations

import os

from aws_lambda_powertools.logging import Logger, correlation_paths
from aws_lambda_powertools.tracing import Tracer
from aws_lambda_powertools.utilities.data_classes import (
    LambdaFunctionUrlEvent,
    event_source,
)
from aws_lambda_powertools.utilities.typing import LambdaContext
from mangum import Mangum

from .server import app

logger = Logger()
tracer = Tracer()


@logger.inject_lambda_context(correlation_id_path=correlation_paths.LAMBDA_FUNCTION_URL)
@tracer.capture_lambda_handler(capture_response=True)  # type: ignore
@event_source(data_class=LambdaFunctionUrlEvent)
def lambda_handler(
    event: LambdaFunctionUrlEvent, context: LambdaContext
) -> dict | str | None:
    if event.http_method in ["GET", "OPTIONS"]:
        # GraphiQL
        template_path = os.path.join(
            os.path.dirname(__file__), "templates", "graphiql.html"
        )
        with open(template_path) as f:
            template = f.read()
        html = template.replace(
            "{{ WEBSOCKET_ENDPOINT }}", os.environ["WEBSOCKET_ENDPOINT"]
        )
        return {
            "body": html,
            "statusCode": 200,
            "headers": {"Content-Type": "text/html"},
        }
    elif event.http_method == "POST":
        # Calculate ASGI response from FastAPI via Mangum's lambda handler
        mangum_handler = Mangum(app=app)
        response = mangum_handler(
            event=event._data,
            context=context,  # type: ignore
        )
        return response
    else:
        raise Exception("Unsupported HTTP method")


if __name__ == "__main__":
    context = LambdaContext()
    context._function_name = "test"
    context._memory_limit_in_mb = 512
    context._invoked_function_arn = "test"
    context._aws_request_id = "test"

    event = LambdaFunctionUrlEvent(data={"requestContext": {"http": {"method": "GET"}}})

    lambda_handler(event=event, context=context)
