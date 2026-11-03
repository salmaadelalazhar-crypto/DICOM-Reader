from pathlib import Path
import streamlit as st
from streamlit.components.v1 import declare_component

_component = declare_component('desktop_direct_speech', path=str(Path(__file__).with_name('speech_component')))


def speech_to_text(language='ar', start_prompt='', stop_prompt='', just_once=True, key='mg_stt'):
    value = _component(language=language, start_prompt=start_prompt, stop_prompt=stop_prompt, just_once=just_once, key=key, default=None)
    if value and value.get('id') != st.session_state.get(key + '_consumed'):
        st.session_state[key + '_consumed'] = value['id']
        return value['text']
    return None
