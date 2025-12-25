"""Streamlit entrypoint.

Run: `streamlit run app.py`
"""

import runpy

runpy.run_module("child_story_maker.frontend.streamlit_app", run_name="__main__")
