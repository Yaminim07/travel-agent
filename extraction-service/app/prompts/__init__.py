"""All LLM prompts live here, one module per purpose."""
from .answer_prompt import ANSWER_PROMPT
from .destination_prompt import DESTINATION_PROMPT
from .extraction_prompt import SYSTEM_CONTEXT
from .router_prompt import ROUTER_PROMPT

__all__ = ["ANSWER_PROMPT", "DESTINATION_PROMPT", "ROUTER_PROMPT", "SYSTEM_CONTEXT"]
