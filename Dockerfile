ARG PYTHON_VERSION=3.9
# https://docs.aws.amazon.com/lambda/latest/dg/python-image.html#python-image-base
FROM amazon/aws-lambda-python:${PYTHON_VERSION} AS base

# Install Poetry package manager
ENV POETRY_VERSION="1.4.2"
RUN curl -sSL https://install.python-poetry.org/ | python3 && rm -rf ~/.cache
ENV PATH="~/.local/bin:$PATH"
RUN poetry config virtualenvs.create false

# Install Poetry dependencies
COPY ./pyproject.toml ./poetry.lock ./
RUN poetry install --no-root --no-interaction --only main

COPY ./api ./api

# CMD defined in the Pulumi code