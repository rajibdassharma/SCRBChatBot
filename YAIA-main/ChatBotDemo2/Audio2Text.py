import speech_recognition
import streamlit as st
 

def voice_to_text(): 
    # The Recognizer is initialized.
    UserVoiceRecognizer = speech_recognition.Recognizer()
    
#   while(1):
    try:
        with speech_recognition.Microphone() as UserVoiceInputSource:

            UserVoiceRecognizer.adjust_for_ambient_noise(UserVoiceInputSource, duration=0.5)
            st.write("Preparing to record")

            # The Program listens to the user voice input.
            UserVoiceInput = UserVoiceRecognizer.listen(UserVoiceInputSource)

            UserVoiceInput_converted_to_Text = UserVoiceRecognizer.recognize_google(UserVoiceInput)
            UserVoiceInput_converted_to_Text = UserVoiceInput_converted_to_Text.lower()
            st.session_state.voice_text_input = UserVoiceInput_converted_to_Text
            st.write(UserVoiceInput_converted_to_Text)
            return UserVoiceInput_converted_to_Text
    except KeyboardInterrupt:
        print('A KeyboardInterrupt encountered; Terminating the Program !!!')
        exit(0)
    
    except speech_recognition.UnknownValueError:
        print("No User Voice detected OR unintelligible noises detected OR the recognized audio cannot be matched to text !!!")     
    
