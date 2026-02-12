from dataclasses import dataclass
from typing import List  # NOQA: UP035

from .constants import AI_ROLE_OPTIONS

@dataclass
class Locale:
    ai_role_options: List[str]
    ai_role_prefix: str
    ai_role_postfix: str
    title: str
    language: str
    lang_code: str
    chat_placeholder: str
    chat_run_btn: str
    chat_clear_btn: str
    chat_save_btn: str
    speak_btn: str
    input_kind: str
    input_kind_1: str
    input_kind_2: str
    select_placeholder1: str
    select_placeholder2: str
    select_placeholder3: str
    radio_placeholder: str
    radio_text1: str
    radio_text2: str
    stt_placeholder: str
    footer_title: str
    footer_option0: str
    footer_option1: str
    footer_option2: str
    footer_option3: str
    footer_option4: str
    footer_option5: str
    footer_chat: str
    footer_channel: str


# --- LOCALE SETTINGS ---
en = Locale(
    ai_role_options=AI_ROLE_OPTIONS,
    ai_role_prefix="You are a female",
    ai_role_postfix="Answer as concisely as possible.",
    title="Your AI Assistant 1.0",
    language="English",
    lang_code="en",
    chat_placeholder="Ask Your AI Assistant:",
    chat_run_btn="Ask",
    chat_clear_btn="Clear",
    chat_save_btn="Save Chat",
    speak_btn="Push to Speak",
    input_kind="Input Kind",
    input_kind_1="Text",
    input_kind_2="Voice [test mode]",
    select_placeholder1="Select Text Model",
    select_placeholder2="Select Role",
    select_placeholder3="Select Image Model",
    radio_placeholder="Select Input Kind",
    radio_text1="Text",
    radio_text2="Voice",
    stt_placeholder="To Hear The Voice Of AI Press Play",
    footer_title="Support & Feedback",
    footer_option0="Upload",
    footer_option1="Chat",
    footer_option2="Generate",
    footer_option3="Search",
    footer_option4="Prompts",
    footer_option5="About",
    footer_chat="AI Talks Chat",
    footer_channel="AI Talks Channel",
)


