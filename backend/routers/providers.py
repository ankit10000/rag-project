"""Provider/model configuration (read-only).

The repository implements ONE provider today: Gemini (services/llm_service.py).
Batch 1: settings come from services/llm_config.py, the same module the
provider implementation uses (no SDK import, no client, no key check), instead
of parsing llm_service.py with ``ast``. The values reported are the effective
in-process settings (process environment > .env > code default). API key
VALUES are never read into responses — only whether a key is configured.
Writing provider settings or credentials is not exposed.
"""

from fastapi import APIRouter

from backend.schemas import ProviderInfo, ProvidersResponse

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("", response_model=ProvidersResponse)
def list_providers():
    from services import llm_config

    return ProvidersResponse(
        providers=[ProviderInfo(
            name=llm_config.PROVIDER_NAME,
            implemented=True,
            api_key_configured=llm_config.api_key_configured(),
            primary_model=llm_config.MODEL_NAME,
            fallback_models=list(llm_config.FALLBACK_MODELS),
            settings_source={
                "GEMINI_MODEL": llm_config.setting_source("GEMINI_MODEL"),
                "GEMINI_FALLBACK_MODELS": llm_config.setting_source("GEMINI_FALLBACK_MODELS"),
            },
        )],
        write_support=False,
        note=("Only the Gemini provider is implemented in this repository. Provider/model changes and "
              "credential management are not exposed through the API; fallback policy is unchanged."),
    )
