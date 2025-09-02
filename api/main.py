import os
import requests
import re
from urllib.parse import urlparse, quote_plus, urljoin
import chardet
from bs4 import BeautifulSoup
import base64
from flask import Flask, request, render_template, redirect, url_for, Response

app = Flask(__name__)
app.secret_key = os.urandom(24) # A proper secret key

def rewrite_html(content, target_url):
    """
    Parses the HTML and rewrites all URLs to be proxied.
    """
    try:
        soup = BeautifulSoup(content, 'lxml')
    except Exception as e:
        print(f"BeautifulSoup parsing error: {e}")
        return content

    # Define tags and attributes to rewrite
    tags_to_rewrite = {
        'a': 'href',
        'link': 'href',
        'script': 'src',
        'img': 'src',
        'source': 'src',
        'iframe': 'src',
    }
    
    parsed_url = urlparse(target_url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

    for tag, attr in tags_to_rewrite.items():
        for element in soup.find_all(tag, **{attr: True}):
            url = element.get(attr)
            if url:
                # Special handling for anchor links (#)
                if url.startswith('#'):
                    continue
                # For relative URLs, make them absolute before encoding
                if not url.startswith('http'):
                    url = urljoin(base_url, url)
                
                # Encode the URL for the proxy
                encoded_url = base64.urlsafe_b64encode(url.encode()).decode()
                element[attr] = url_for('serve_proxy_encoded', encoded_url=encoded_url)

    # Rewrite forms to POST to the proxy endpoint
    for form in soup.find_all('form', action=True):
        action_url = form.get('action')
        if not action_url.startswith('http'):
            action_url = urljoin(base_url, action_url)
        
        encoded_url = base64.urlsafe_b64encode(action_url.encode()).decode()
        form['action'] = url_for('proxy_post', encoded_url=encoded_url)

    # Rewrite style URLs within the style tags
    for style_tag in soup.find_all('style'):
        style_content = style_tag.string
        if style_content:
            style_content = re.sub(
                r'url\((["\']?)(.*?)\1\)',
                lambda match: f'url({match.group(1)}{url_for("serve_proxy_encoded", encoded_url=base64.urlsafe_b64encode(urljoin(base_url, match.group(2)).encode()).decode())}{match.group(1)})',
                style_content
            )
            style_tag.string = style_content
            
    return str(soup)

def proxy_request(target_url, method, data=None):
    """
    A unified function to handle both GET and POST requests.
    """
    print(f"Proxying {method} request for: {target_url}")
    
    # Exclude headers that can cause issues with content encoding and security policies
    excluded_headers = ['connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization', 'te', 'trailers', 'transfer-encoding', 'upgrade', 'x-frame-options', 'content-security-policy', 'accept-encoding']
    headers = {key: value for key, value in request.headers.items() if key.lower() not in excluded_headers}

    try:
        if method == 'GET':
            response = requests.get(target_url, headers=headers, timeout=10)
        elif method == 'POST':
            response = requests.post(target_url, headers=headers, data=data, timeout=10)
        else:
            return "Error: Unsupported HTTP method", 405

        # Detect encoding and decode the content
        encoding = chardet.detect(response.content)['encoding'] or 'utf-8'
        content = response.content.decode(encoding, errors='ignore')
        
        # Rewrite the content
        rewritten_content = rewrite_html(content, target_url)

        # Create a Flask response object with the modified content
        flask_response = Response(rewritten_content, status=response.status_code)

        # Copy over useful headers, excluding security headers
        for key, value in response.headers.items():
            if key.lower() not in excluded_headers:
                flask_response.headers[key] = value

        # Set a relaxed Content-Security-Policy
        flask_response.headers['Content-Security-Policy'] = "default-src 'self' 'unsafe-inline' 'unsafe-eval' data:; connect-src *; style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; img-src * data:; script-src 'self' 'unsafe-inline' 'unsafe-eval';"
        flask_response.headers['Content-Type'] = 'text/html; charset=utf-8'

        return flask_response

    except requests.exceptions.RequestException as e:
        print(f"Proxy Error: {e}")
        return f"<h1>Proxy Error</h1><p>Could not connect to the requested URL: {target_url}</p><p>Details: {e}</p>", 502

# --- Routes ---

@app.route('/')
def home():
    """Renders the main page with the embedded HTML template."""
    return render_template('index.html')

@app.route('/proxy', methods=['POST'])
def handle_proxy_request():
    """
    Handles the POST request from the search bar.
    It determines if the input is a URL or a search query and redirects accordingly.
    """
    url_input = request.form.get('url', '').strip()
    
    # Check if the input is a valid URL
    if re.match(r'^https?://', url_input):
        encoded_url = base64.urlsafe_b64encode(url_input.encode()).decode()
        return redirect(url_for('serve_proxy_encoded', encoded_url=encoded_url))
    elif '.' in url_input:
        # A simple check for a domain name (e.g., google.com)
        url = f'http://{url_input}'
        encoded_url = base64.urlsafe_b64encode(url.encode()).decode()
        return redirect(url_for('serve_proxy_encoded', encoded_url=encoded_url))
    else:
        # Assume it's a search query and redirect to Google
        search_query = quote_plus(url_input)
        search_url = f'https://www.google.com/search?q={search_query}'
        encoded_url = base64.urlsafe_b64encode(search_url.encode()).decode()
        return redirect(url_for('serve_proxy_encoded', encoded_url=encoded_url))

@app.route('/serve_proxy/<encoded_url>', methods=['GET'])
def serve_proxy_encoded(encoded_url):
    """
    Fetches the content from the target URL (decoded), rewrites it, and serves it.
    """
    try:
        target_url = base64.urlsafe_b64decode(encoded_url.encode()).decode()
    except (base64.binascii.Error, UnicodeDecodeError):
        return "Invalid URL format", 400

    return proxy_request(target_url, 'GET')

@app.route('/proxy_post/<encoded_url>', methods=['POST'])
def proxy_post(encoded_url):
    """
    Handles POST requests from proxied forms and forwards them to the target URL.
    """
    try:
        target_url = base64.urlsafe_b64decode(encoded_url.encode()).decode()
    except (base64.binascii.Error, UnicodeDecodeError):
        return "Invalid URL format", 400

    return proxy_request(target_url, 'POST', data=request.form)
