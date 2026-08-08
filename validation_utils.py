from fastapi.encoders import jsonable_encoder


def serialize_validation_error_details(error_details):
    """Convert FastAPI validation details into JSON-safe structures."""
    return jsonable_encoder(
        error_details,
        custom_encoder={
            bytes: lambda value: value.decode("utf-8", errors="replace"),
            BaseException: lambda exc: str(exc),
        },
    )
