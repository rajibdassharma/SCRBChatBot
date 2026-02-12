
# Later on update this to configure during onboarding based upon the nature of the application
AI_MODEL_OPTIONS: list[str] = [
    "OpenAI gpt-3.5 turbo",
    #"OpenAI gpt-4",
    #"OpenAI gpt-4-32k",
    "Hugging Face"
]
AI_ROLE_OPTIONS: list[str] = [
    "Helpful Assistant",
#    "code assistant",
#    "code reviewer",
#    "text improver",
#    "English grammar expert",
#    "friendly and helpful teaching assistant",
#    "translate corporate jargon into plain English",
]
AI_DOMAIN_OPTIONS: list[str] = ["Select", "Enterprise", "HR","Finance","Education","Sales","Marketing","Operations","Training", "Technical Publications"]
AI_ROLE_OPTIONS: list[str] = ["Select", "admin", "team", "user"]
AI_GENERATE_OPTIONS: list[str] = ["Tweet", "Image", "Video", "Audio", "LinkedIn Post", "Facebook Post", "eMail"]
AI_IMAGE_MODEL_OPTIONS: list[str] = ["DALL-E 2", "Hugging Face"]
AI_IMAGE_RES_OPTIONS: list[str] = ["256x256", "512x512", "1024x1024"]

DATA_DIR = "/Users/rajibdassharma/YAIA/data" 
