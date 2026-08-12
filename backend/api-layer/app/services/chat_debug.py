ADMIN_DEBUG_ROLES = {"admin", "administrator", "superuser"}
DEBUG_ENVIRONMENTS = {"development", "local", "dev"}


def can_include_chat_response_debug(*, enable_debug: bool, environment: str, role: object) -> bool:
    if not enable_debug:
        return False

    normalized_environment = str(environment or "").lower()
    normalized_role = str(role or "").lower()

    return normalized_environment in DEBUG_ENVIRONMENTS or normalized_role in ADMIN_DEBUG_ROLES
