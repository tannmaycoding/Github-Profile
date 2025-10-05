# app.py — Streamlit GitHub profile + repos + README viewer
import os
import base64
import requests
import streamlit as st
import pandas as pd
from typing import List, Dict, Any
from dotenv import load_dotenv

load_dotenv()

GITHUB_API = "https://api.github.com"

# IMPORTANT: do NOT hardcode tokens. Set the environment variable GITHUB_TOKEN if you want auth.
TOKEN = os.environ.get("GITHUB-TOKEN")

HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
if TOKEN:
    HEADERS["Authorization"] = f"Bearer {TOKEN}"


@st.cache_data(ttl=300)
def get_user(username: str) -> Dict[str, Any]:
    """Get public profile data for a username"""
    url = f"{GITHUB_API}/users/{username}"
    r = requests.get(url, headers=HEADERS)
    r.raise_for_status()
    return r.json()


@st.cache_data(ttl=300)
def list_user_repos(username: str, per_page: int = 100) -> List[Dict[str, Any]]:
    """List repositories for a user (handles pagination)."""
    repos = []
    page = 1
    while True:
        url = f"{GITHUB_API}/users/{username}/repos"
        params = {"per_page": per_page, "page": page, "type": "all", "sort": "updated"}
        r = requests.get(url, headers=HEADERS, params=params)
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        repos.extend(batch)
        if len(batch) < per_page:
            break
        page += 1
    return repos


@st.cache_data(ttl=300)
def get_readme(owner: str, repo: str, raw: bool = True) -> str:
    """
    Get README for repo.
    If raw=True, request the raw contents directly (returns text).
    Otherwise, returns decoded content from the JSON payload.
    """
    url = f"{GITHUB_API}/repos/{owner}/{repo}/readme"
    headers = HEADERS.copy()
    if raw:
        headers["Accept"] = "application/vnd.github.v3.raw"
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        return r.text
    else:
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        data = r.json()
        content_b64 = data.get("content", "")
        return base64.b64decode(content_b64).decode("utf-8", errors="replace")


def make_repo_dataframe(repos: List[Dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for r in repos:
        rows.append(
            {
                "name": r.get("name"),
                "description": r.get("description"),
                "language": r.get("language"),
                "stars": r.get("stargazers_count", 0),
                "forks": r.get("forks_count", 0),
                "updated_at": r.get("updated_at"),
                "html_url": r.get("html_url"),
                "private": r.get("private", False),
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(by=["stars", "updated_at"], ascending=[False, False])
    return df


# ---------------- Streamlit UI ----------------
st.set_page_config(page_title="GitHub Explorer", layout="wide")
st.title("🔎 GitHub Explorer — profile, repos, and README")

if "searched_user" not in st.session_state:
    st.session_state["searched_user"] = ""

with st.form("search_form"):
    username_input = st.text_input("GitHub username", value="meta")
    raw_readme = st.checkbox("Fetch README as raw text (recommended)", value=True)
    submitted = st.form_submit_button("Search")
    if submitted:
        st.session_state["searched_user"] = username_input

username = st.session_state["searched_user"]
if not username:
    st.info("Enter a GitHub username above and click Search.")
    st.stop()

# Main content
try:
    user = get_user(username)
except requests.HTTPError as e:
    st.error(f"Failed to fetch user `{username}`: {e}")
    st.stop()
except Exception as e:
    st.error(f"Unexpected error: {e}")
    st.stop()

col1, col2 = st.columns([1, 3])
with col1:
    avatar_url = user.get("avatar_url")
    if avatar_url:
        st.image(avatar_url, width=160)
    st.markdown(f"### [{user.get('login')}]({user.get('html_url')})")
    if user.get("name"):
        st.write(user.get("name"))
    if user.get("bio"):
        st.write(user.get("bio"))
    st.write(
        f"Followers: **{user.get('followers', 0)}**  •  Following: **{user.get('following', 0)}**"
    )
    if user.get("company"):
        st.write(f"Company: {user.get('company')}")
    if user.get("location"):
        st.write(f"Location: {user.get('location')}")
    if user.get("blog"):
        st.write(f"[Blog/Website]({user.get('blog')})")

with col2:
    st.header("Repositories")
    try:
        repos = list_user_repos(username)
    except requests.HTTPError as e:
        st.error(f"Failed to list repos for `{username}`: {e}")
        st.stop()
    df = make_repo_dataframe(repos)
    df_func = lambda dataframe: dataframe.to_csv().encode("utf-8")
    st.download_button(label="Download Repo Data",
                       data=df_func(df),
                       file_name="data.csv",
                       mime="text/csv",
                       icon=":material/download:",)

    if df.empty:
        st.write("No repositories found.")
    else:
        for idx, row in enumerate(df.itertuples()):
            container = st.container(border=True)
            container.markdown(f"## [{row.name}]({row.html_url})")
            if row.description:
                container.write(row.description)

            # Show metrics side by side
            col1, col2, col3 = container.columns(3)
            col1.metric("⭐ Stars", row.stars)
            col2.metric("🍴 Forks", row.forks)
            col3.metric("💻 Language", row.language if row.language else "N/A")

            # README button with a unique key
            if container.button("Get README", key=f"get_{row.name}_{idx}"):
                with container.expander("Show README"):
                    try:
                        st.markdown(
                            get_readme(user.get("login"), row.name, raw=raw_readme),
                            unsafe_allow_html=False,
                        )
                    except:
                        st.error("README not found")

        # repo selection
        st.markdown("# Get README")
        repo_names = df["name"].tolist()
        selected_repo = st.selectbox("Select repository to view README", repo_names)

        if selected_repo:
            owner = user.get("login")
            try:
                readme_text = get_readme(owner, selected_repo, raw=raw_readme)
                st.markdown(f"## README — `{owner}/{selected_repo}`")
                # Render markdown safely; README is usually Markdown
                st.markdown(readme_text, unsafe_allow_html=False)
                # provide download link
                b64 = base64.b64encode(readme_text.encode()).decode()
                href = f'<a href="data:text/plain;base64,{b64}" download="{selected_repo}_README.md">Download README</a>'
                st.markdown(href, unsafe_allow_html=True)
            except requests.HTTPError as e:
                st.warning(f"No README or cannot access README for {selected_repo}: {e}")
            except Exception as e:
                st.error(f"Error fetching README: {e}")
