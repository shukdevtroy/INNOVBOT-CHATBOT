import streamlit as st
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re
from openai import OpenAI
import time
import copy

# Set page configuration
st.set_page_config(
    page_title="InnovativeSkills Bangladesh Chatbot",
    page_icon="💬",
    layout="wide"
)

# Function to check if URL belongs to the website
def is_valid_url(url, base_url):
    parsed_url = urlparse(url)
    parsed_base = urlparse(base_url)
    return parsed_url.netloc == parsed_base.netloc

# Function to scrape content from a single page
def scrape_page(url):
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Remove script, style elements and comments
            for element in soup(['script', 'style', 'header', 'footer', 'nav']):
                element.decompose()
                
            # Get text content
            text = soup.get_text(separator=' ', strip=True)
            
            # Clean up whitespace
            text = re.sub(r'\s+', ' ', text).strip()
            
            return text
        else:
            return None
    except Exception as e:
        st.error(f"Error scraping {url}: {e}")
        return None

# Function to crawl website and get all links
@st.cache_data
def crawl_website(base_url, max_pages=80):
    st.info(f"Starting to crawl {base_url}")
    visited_urls = set()
    urls_to_visit = [base_url]
    site_content = {}
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    while urls_to_visit and len(visited_urls) < max_pages:
        current_url = urls_to_visit.pop(0)
        
        if current_url in visited_urls:
            continue
            
        status_text.text(f"Crawling: {current_url}")
        visited_urls.add(current_url)
        
        try:
            response = requests.get(current_url, timeout=10)
            if response.status_code == 200:
                # Get content of the current page
                content = scrape_page(current_url)
                if content:
                    site_content[current_url] = content
                
                # Find all links on the page
                soup = BeautifulSoup(response.text, 'html.parser')
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    full_url = urljoin(current_url, href)
                    
                    # Only follow links that are part of the same website
                    if is_valid_url(full_url, base_url) and full_url not in visited_urls:
                        urls_to_visit.append(full_url)
            
            # Add a small delay to be respectful
            time.sleep(0.5)
            
            # Update progress
            progress = min(len(visited_urls) / max_pages, 1.0)
            progress_bar.progress(progress)
            
        except Exception as e:
            st.error(f"Error visiting {current_url}: {e}")
    
    status_text.text(f"Crawled {len(visited_urls)} pages and collected content from {len(site_content)} pages.")
    progress_bar.empty()
    
    return site_content

# Function that creates a context from the scraped content
def create_context(site_content, max_context_length=8000):
    context = "Content from https://innovativeskillsbd.com website:\n\n"
    
    for url, content in site_content.items():
        # Add URL and a portion of its content (limited to keep context manageable)
        page_content = f"Page: {url}\n{content[:1000]}...\n\n"
        
        # Check if adding this would exceed max context length
        if len(context) + len(page_content) > max_context_length:
            break
            
        context += page_content
    
    return context

# Function to fix URLs in text to ensure they point to the correct domain
def fix_urls_in_text(text):
    # Look for URLs in the text
    url_pattern = r'https?://[^\s/$.?#].[^\s]*'
    urls = re.findall(url_pattern, text)
    
    for url in urls:
        # If the URL contains the wrong domain but appears to be an InnovativeSkills link
        if ('innovative-skill.com' in url or 'innovativeskill.com' in url) and 'innovativeskillsbd.com' not in url:
            # Create the correct URL by replacing the domain
            path = urlparse(url).path
            correct_url = f"https://innovativeskillsbd.com{path}"
            # Replace in the text
            text = text.replace(url, correct_url)
    
    return text

# Function to query the DeepSeek V3 model
def query_model(api_key, messages):
    try:
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
        
        completion = client.chat.completions.create(
            extra_headers={
                "HTTP-Referer": "https://innovativeskillsbd.com",
                "X-Title": "InnovativeSkills ChatBot",
            },
            model="deepseek/deepseek-chat-v3-0324:free",
            messages=messages
        )
        
        response = completion.choices[0].message.content
        
        # Fix any incorrect URLs - ensure all links point to the correct domain
        response = fix_urls_in_text(response)
        
        return response
    except Exception as e:
        return f"Error querying the model: {str(e)}"

# Function to answer questions based on website content
def answer_question(api_key, question, site_content):
    if not api_key:
        return "Please enter your OpenRouter API key."
    
    # Prepare the context from scraped content
    context = create_context(site_content)
    
    # Create system message with context
    system_message = {
        "role": "system", 
        "content": f"""You are a helpful AI assistant for InnovativeSkills Bangladesh, a website focused on helping people learn IT skills. 
        Use the following content from the website to answer user questions. If the question is not related to the website or the 
        information is not available in the content, politely say so and try to provide general guidance related to InnovativeSkills.
        
        IMPORTANT: When referring to any URLs related to the website, ALWAYS use the domain 'innovativeskillsbd.com' (NOT 'innovative-skill.com' or 'innovativeskill.com').
        For example, use 'https://innovativeskillsbd.com/student-job-success' instead of any other domain.
        
        {context}"""
    }
    
    # Create message history for the API call
    messages = [system_message]
    
    # Add conversation history from session state
    for message in st.session_state.conversation:
        role = message["role"]
        content = message["content"]
        messages.append({"role": role, "content": content})
    
    # Add current question
    messages.append({"role": "user", "content": question})
    
    # Query the model
    response = query_model(api_key, messages)
    
    return response

# Initialize session state for conversation history
if "conversation" not in st.session_state:
    st.session_state.conversation = []

if "site_content" not in st.session_state:
    st.session_state.site_content = {}

# Main app UI
st.title("InnovativeSkills Bangladesh Chatbot")
st.markdown("This chatbot uses DeepSeek V3 to answer questions about InnovativeSkills Bangladesh website.")

# Sidebar for API key and website crawling options
with st.sidebar:
    st.header("Settings")
    api_key = st.text_input("OpenRouter API Key", type="password")
    
    st.subheader("Website Crawler")
    if st.button("Crawl Website") or not st.session_state.site_content:
        with st.spinner("Crawling InnovativeSkills website..."):
            st.session_state.site_content = crawl_website("https://innovativeskillsbd.com/")
    
    if st.button("Clear Conversation"):
        st.session_state.conversation = []
        st.experimental_rerun()

# Display conversation
for message in st.session_state.conversation:
    role = message["role"]
    content = message["content"]
    
    if role == "user":
        st.chat_message("user").write(content)
    else:  # assistant
        st.chat_message("assistant").write(content)

# Chat input
user_question = st.chat_input("Ask a question about InnovativeSkills Bangladesh")

if user_question:
    # Add user message to conversation
    st.session_state.conversation.append({"role": "user", "content": user_question})
    
    # Display user message
    st.chat_message("user").write(user_question)
    
    # Generate and display assistant response
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            response = answer_question(api_key, user_question, st.session_state.site_content)
            st.write(response)
    
    # Add assistant response to conversation
    st.session_state.conversation.append({"role": "assistant", "content": response})
