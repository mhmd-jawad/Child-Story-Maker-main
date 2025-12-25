# app.py
import streamlit as st
from copy import deepcopy
from child_story_maker.common.utils import *
from child_story_maker.frontend.api_client import story_generation, image_generation
from child_story_maker.common.db import (
    init_db,
    create_parent,
    authenticate_parent,
    list_children,
    create_child,
    delete_child,
    get_child,
)


# ======================== SETUP ========================

# -----------------------------
# App Metadata
# -----------------------------
APP_TITLE = "Magical Story Builder"
APP_TAGLINE = "Create wonderful, illustrated stories from your imagination!"

st.set_page_config(page_title=APP_TITLE, page_icon=":book:", layout="wide")

# -----------------------------
# Session state
# -----------------------------
if "story" not in st.session_state:
    st.session_state.story = None
if "cover_img_bytes" not in st.session_state:
    st.session_state.cover_img_bytes = None
if "parent_id" not in st.session_state:
    st.session_state.parent_id = None
if "parent_email" not in st.session_state:
    st.session_state.parent_email = None
if "active_child_id" not in st.session_state:
    st.session_state.active_child_id = None

init_db()

# -----------------------------
# Styling
# -----------------------------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;700&family=Space+Grotesk:wght@400;500;600;700&display=swap');
    :root {
        --bg-1: #f6f1ea;
        --bg-2: #fff1de;
        --ink: #1f2937;
        --muted: #6b7280;
        --accent: #0f766e;
        --accent-2: #f97316;
        --panel: #ffffff;
        --panel-border: #ead8c6;
        --shadow: 0 16px 40px rgba(30, 41, 59, 0.12);
    }
    html, body, [class*="stApp"] {
        font-family: "Space Grotesk", "Segoe UI", sans-serif;
        color: var(--ink);
    }
    .stApp {
        background: radial-gradient(circle at 15% 10%, #fff6eb 0, #f6f1ea 38%, #fef3e2 100%);
    }
    .block-container {
        padding-top: 2.2rem;
        padding-bottom: 3rem;
        max-width: 1200px;
    }
    section[data-testid="stSidebar"] > div {
        background: #fff5e6;
        border-right: 1px solid #f3d6b6;
    }
    .hero {
        position: relative;
        padding: 2.2rem 2rem;
        background: linear-gradient(120deg, #fff3e0 0%, #ffe9d2 40%, #e2f5f1 100%);
        border: 1px solid #f3d6b6;
        border-radius: 24px;
        box-shadow: var(--shadow);
        overflow: hidden;
    }
    .hero-title {
        font-family: "Fraunces", "Times New Roman", serif;
        font-size: 2.3rem;
        margin: 0 0 0.3rem 0;
    }
    .hero-sub {
        color: var(--muted);
        font-size: 1.05rem;
        max-width: 46rem;
    }
    .hero-kicker {
        text-transform: uppercase;
        letter-spacing: 0.16em;
        font-size: 0.75rem;
        color: #9a6b2f;
        margin-bottom: 0.4rem;
    }
    .hero-orb {
        position: absolute;
        border-radius: 999px;
        opacity: 0.5;
    }
    .hero-orb--one {
        width: 180px;
        height: 180px;
        background: #ffedd5;
        top: -60px;
        right: 10px;
    }
    .hero-orb--two {
        width: 120px;
        height: 120px;
        background: #ccfbf1;
        bottom: -50px;
        left: 60px;
    }
    .panel {
        background: var(--panel);
        border: 1px solid var(--panel-border);
        border-radius: 20px;
        padding: 1.4rem 1.6rem;
        box-shadow: 0 12px 30px rgba(16, 24, 40, 0.08);
    }
    .panel + .panel {
        margin-top: 1.2rem;
    }
    .section-title {
        font-weight: 600;
        font-size: 1.1rem;
        margin: 0 0 0.8rem 0;
    }
    .sidebar-title {
        font-size: 1.1rem;
        font-weight: 700;
        color: #7c4a12;
    }
    .sidebar-sub {
        font-size: 0.9rem;
        color: #8b6a44;
        margin-top: 0.3rem;
    }
    .stTabs [data-baseweb="tab"] {
        background: #fff0e0;
        color: #3b2f2f;
        border-radius: 999px;
        margin-right: 6px;
        font-weight: 600;
        font-size: 0.95rem;
        border: 1px solid #f3d6b6;
        padding: 0.2rem 0.85rem;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(90deg, #0f766e 0%, #f97316 100%);
        color: #fff;
        border: none;
    }
    .stButton>button, .stDownloadButton>button {
        background: linear-gradient(90deg, #0f766e 0%, #f97316 100%);
        color: white;
        border: none;
        border-radius: 12px;
        font-weight: 600;
        font-size: 1rem;
        padding: 0.6rem 1.3rem;
        box-shadow: 0 8px 20px rgba(15, 118, 110, 0.2);
        transition: 0.2s;
    }
    .stButton>button:hover, .stDownloadButton>button:hover {
        filter: brightness(1.03);
        transform: translateY(-1px);
    }
    .stTextInput>div>div>input, .stTextArea textarea {
        background: #fff8f0;
        border-radius: 10px;
        border: 1.5px solid #f3d6b6;
        color: #222;
        font-size: 1.05rem;
    }
    .stSelectbox>div>div>div>div {
        background: #fff8f0;
        border-radius: 10px;
        color: #222;
        border: 1.5px solid #f3d6b6;
    }
    .stSlider>div>div>div>div {
        background: #0f766e;
    }
    .stAlert {
        border-radius: 14px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def _logout() -> None:
    st.session_state.parent_id = None
    st.session_state.parent_email = None
    st.session_state.active_child_id = None
    st.session_state.story = None
    st.session_state.cover_img_bytes = None
    st.rerun()

children = []
active_child = None
if st.session_state.parent_id:
    children = list_children(st.session_state.parent_id)
    if children and not st.session_state.active_child_id:
        st.session_state.active_child_id = int(children[0]["id"])
    if st.session_state.active_child_id:
        active_child = get_child(
            st.session_state.parent_id, st.session_state.active_child_id
        )

# -----------------------------
# Sidebar: Story settings
# -----------------------------
with st.sidebar:
    if st.session_state.parent_id:
        st.markdown(
            """
            <div style='padding:0.5rem 0;'>
                <div class='sidebar-title'>Parent Account</div>
                <div class='sidebar-sub'>Signed in.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.caption(st.session_state.parent_email or "")
        if st.button("Log out"):
            _logout()

        st.markdown("### Child Profiles")
        if children:
            child_labels = [
                f"{c['name']} (age {c['age']})" for c in children
            ]
            id_by_label = {
                f"{c['name']} (age {c['age']})": int(c["id"]) for c in children
            }
            default_index = 0
            if st.session_state.active_child_id:
                for idx, c in enumerate(children):
                    if int(c["id"]) == st.session_state.active_child_id:
                        default_index = idx
                        break
            selected_label = st.selectbox(
                "Active child",
                child_labels,
                index=default_index,
            )
            selected_id = id_by_label.get(selected_label)
            if selected_id and selected_id != st.session_state.active_child_id:
                st.session_state.active_child_id = selected_id
                active_child = get_child(
                    st.session_state.parent_id, st.session_state.active_child_id
                )
        else:
            st.info("Add a child profile to personalize stories.")

        with st.expander("Add child profile"):
            with st.form("add_child_form"):
                child_name = st.text_input("Child name")
                child_age = st.number_input(
                    "Age", min_value=2, max_value=12, value=6, step=1
                )
                child_interests = st.text_input(
                    "Interests (comma-separated)", placeholder="space, animals, friends"
                )
                create_child_btn = st.form_submit_button("Create profile")
            if create_child_btn:
                try:
                    new_id = create_child(
                        st.session_state.parent_id,
                        child_name,
                        int(child_age),
                        child_interests,
                    )
                    st.session_state.active_child_id = new_id
                    st.success("Child profile created.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

        if active_child:
            if st.button("Delete selected child"):
                delete_child(st.session_state.parent_id, int(active_child["id"]))
                st.session_state.active_child_id = None
                st.rerun()

        st.markdown("---")
    else:
        st.info("Sign in to manage child profiles.")

    st.markdown(
        """
        <div style='padding:0.5rem 0;'>
            <div class='sidebar-title'>Story Settings</div>
            <div class='sidebar-sub'>Tune age, tone, and visuals.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if active_child:
        child_age_group = age_to_group(int(active_child["age"]))
        age_index = list(AGE_LEVEL_HINTS.keys()).index(child_age_group)
        age_group = st.selectbox(
            "Target age", list(AGE_LEVEL_HINTS.keys()), index=age_index, disabled=True
        )
    else:
        age_group = st.selectbox("Target age", list(AGE_LEVEL_HINTS.keys()), index=0)
    language = st.selectbox("Language", LANG_CHOICES, index=0)
    style = st.selectbox("Tone / style", STYLE_CHOICES, index=0)
    img_style = st.selectbox("Image style", IMG_STYLE_CHOICES, index=1)
    n_chapters = st.slider("Chapters", 1, 8, 4)
    seed = st.number_input("Seed (optional)", value=0, min_value=0, step=1)

    st.markdown("### Character")
    if active_child:
        char_name = str(active_child["name"])
        st.text_input("Main character name", char_name, disabled=True)
        if active_child["interests"]:
            st.caption(f"Interests: {active_child['interests']}")
    else:
        char_name = st.text_input("Main character name", "")
    char_traits = st.text_input("2-3 traits (comma-separated)", "curious, kind")
    setting = st.text_input("Setting", "small seaside town")

    st.caption("Tip: Fix the seed to reproduce results when iterating.")

# -----------------------------
# Header
# -----------------------------
st.markdown(
    f"""
    <div class='hero'>
        <span class='hero-orb hero-orb--one'></span>
        <span class='hero-orb hero-orb--two'></span>
        <div class='hero-kicker'>Story Studio</div>
        <div class='hero-title'>{APP_TITLE}</div>
        <div class='hero-sub'>{APP_TAGLINE}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

if not st.session_state.parent_id:
    st.markdown("<div class='panel'>", unsafe_allow_html=True)
    tabs = st.tabs(["Sign in", "Create account"])

    with tabs[0]:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            login_btn = st.form_submit_button("Sign in")
        if login_btn:
            parent_id = authenticate_parent(email, password)
            if parent_id:
                st.session_state.parent_id = parent_id
                st.session_state.parent_email = (email or "").strip().lower()
                st.success("Signed in.")
                st.rerun()
            else:
                st.error("Invalid email or password.")

    with tabs[1]:
        with st.form("register_form"):
            new_email = st.text_input("Email", key="reg_email")
            new_password = st.text_input("Password", type="password", key="reg_password")
            create_btn = st.form_submit_button("Create account")
        if create_btn:
            try:
                parent_id = create_parent(new_email, new_password)
                st.session_state.parent_id = parent_id
                st.session_state.parent_email = (new_email or "").strip().lower()
                st.success("Account created.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()


# ======================== LOGIC STARTS HERE ========================

main_tabs = st.tabs(["Story Builder", "Story Similarity"])

with main_tabs[0]:
    st.markdown("<div class='panel'>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>Story prompt</div>", unsafe_allow_html=True)
    col1, col2 = st.columns([2, 1], gap="large")
    with col1:
        user_prompt = st.text_area(
            "Your idea (prompt)",
            placeholder="A brave cat who wants to touch the moon...",
            height=120,
        )
        title_hint = st.text_input(
            "Optional title override", placeholder="e.g., Luna and the Moon Ladder"
        )

    with col2:
        st.markdown("### Advanced")
        show_guidance = st.checkbox("Show age guidance", value=True)
        if show_guidance:
            st.info(reading_level_for_age(age_group))
        safe_mode = st.checkbox("Kid-safe filter", value=True)
        add_cover = st.checkbox("Generate a cover image", value=True)

    gen = st.button("Generate story")
    st.markdown("</div>", unsafe_allow_html=True)

    child_interests = ""
    child_age = None
    if active_child:
        child_interests = str(active_child["interests"] or "")
        child_age = int(active_child["age"])

    if gen:
        if not user_prompt.strip():
            st.warning("Please enter a prompt to start.")
            st.stop()
        if safe_mode:
            ok, err = kid_safe_prompt(user_prompt)
            if not ok:
                st.error(err)
                st.stop()

        with st.spinner("Creating your story..."):
            story = story_generation(
                prompt=user_prompt,
                title_hint=title_hint,
                age_group=age_group,
                language=language,
                style=style,
                n_chapters=n_chapters,
                seed=seed or None,
                extra_context={
                    "main_character": char_name,
                    "traits": char_traits,
                    "setting": setting,
                    "themes": child_interests,
                    "child_age": child_age,
                },
                image_style=img_style,
            )

        with st.spinner("Painting illustrations..."):
            for ch in story.chapters:
                if not ch.image_url:
                    scene_text = ch.image_prompt or ch.text
                    try:
                        ch.image_bytes = image_generation(ch.title, scene_text, img_style)
                    except Exception as exc:
                        st.warning(f"Image generation failed: {exc}")
                        ch.image_bytes = None

            cover_img_bytes = None
            if add_cover:
                cover_ch = Chapter(
                    title=f"{story.title}", text=f"A {style.lower()} story for {age_group}."
                )
                try:
                    cover_img_bytes = image_generation(
                        cover_ch.title, cover_ch.text, f"{img_style} Cover"
                    )
                except Exception as exc:
                    st.warning(f"Cover image generation failed: {exc}")
                    cover_img_bytes = None

        st.success("Story ready!")
        st.session_state.story = deepcopy(story)
        st.session_state.cover_img_bytes = cover_img_bytes

    if st.session_state.story:
        st.markdown("<div class='panel'>", unsafe_allow_html=True)
        story = st.session_state.story
        cover_img_bytes = st.session_state.cover_img_bytes

        if add_cover and cover_img_bytes:
            st.image(cover_img_bytes, caption="Cover", use_column_width=True)

        chapter_tabs = st.tabs(
            [f"{i+1}. {c.title}" for i, c in enumerate(story.chapters)]
        )
        for tab, ch in zip(chapter_tabs, story.chapters):
            with tab:
                st.markdown(f"### {ch.title}")
                if is_arabic(story.language):
                    st.markdown(
                        rtl_block(ch.text.replace("\n", "<br/>")), unsafe_allow_html=True
                    )
                else:
                    st.write(ch.text)
                if ch.image_bytes:
                    st.image(
                        ch.image_bytes,
                        caption=f"Illustration - {img_style}",
                        use_column_width=True,
                    )
                elif ch.image_url:
                    st.image(
                        ch.image_url,
                        caption=f"Illustration - {img_style}",
                        use_column_width=True,
                    )

        colA, colB, colC = st.columns(3)
        with colA:
            zip_bytes = package_story_downloads(story)
            st.download_button(
                "Download story (ZIP)",
                data=zip_bytes,
                file_name=f"{story.title.replace(' ', '_').lower()}_story.zip",
                mime="application/zip",
            )
        with colC:
            pdf_bytes = build_pdf(story, cover_img_bytes if add_cover else None)
            st.download_button(
                "Download as PDF",
                data=pdf_bytes,
                file_name=f"{story.title.replace(' ', '_').lower()}.pdf",
                mime="application/pdf",
            )
        st.markdown("</div>", unsafe_allow_html=True)

with main_tabs[1]:
    st.markdown("<div class='panel'>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>Story similarity</div>", unsafe_allow_html=True)
    if st.session_state.story:
        try:
            from child_story_maker.ml.similarity import compare_text

            parts = []
            for c in st.session_state.story.chapters:
                parts.append(f"{c.title}\n{c.text}".strip())
            story_text = "\n\n".join(p for p in parts if p)
            result = compare_text(story_text, k=3)
            st.metric(
                "Similarity to corpus average",
                f"{result.similarity_to_average:.3f}",
            )
            stats = result.stats or {}
            stats_parts = []
            if stats.get("rows"):
                stats_parts.append(f"rows: {stats['rows']}")
            if stats.get("avg_desc_chars"):
                stats_parts.append(
                    f"avg desc chars: {stats['avg_desc_chars']:.0f}"
                )
            if stats_parts:
                st.caption("Corpus stats: " + ", ".join(stats_parts))
            if result.is_child_like:
                st.success("Looks similar to the children book corpus.")
            else:
                st.warning("Low similarity to the children book corpus.")

            st.markdown("Top matches:")
            for hit in result.top_k:
                st.write(f"{hit.title} (score {hit.score:.3f})")
                meta = " | ".join(
                    p
                    for p in [
                        hit.author,
                        f"interest age: {hit.interest_age}" if hit.interest_age else "",
                        f"reading age: {hit.reading_age}" if hit.reading_age else "",
                    ]
                    if p
                )
                if meta:
                    st.caption(meta)
                if hit.preview:
                    st.write(hit.preview)
        except Exception as exc:
            st.info(str(exc))
    else:
        st.info("Generate a story in the Story Builder tab to see similarity results.")
    st.markdown("</div>", unsafe_allow_html=True)
