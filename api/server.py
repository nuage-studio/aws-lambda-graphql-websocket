from fastapi import FastAPI
from strawberry.fastapi import GraphQLRouter

from .schema import schema

app = FastAPI()

graphql_router = GraphQLRouter(schema=schema, path="/graphql", graphiql=True)

app.include_router(graphql_router)
