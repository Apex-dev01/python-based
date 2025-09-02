# This file is a more advanced proxy script that attempts to rewrite
# all URLs on a proxied page to make them function correctly.

from flask import Flask, request, render_template_string, redirect, url_for, Response
import requests
import re
from urllib.parse import urlparse, quote_plus, urljoin
import chardet
from bs4 import BeautifulSoup

# The following libraries are required:
# Flask, requests, chardet, beautifulsoup4, and lxml

app = Flask(__name__)
app.secret_key = 'super_secret_key'

# --- HTML Template with Embedded CSS and JS ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Apex Proxy</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
    <style>
        body {
            background-color: #1a1a1a;
            color: #ffffff;
            font-family: 'Inter', sans-serif;
        }
        .container {
            max-width: 900px;
            margin: auto;
        }
        .header {
            background-color: #0d0d0d;
            border-bottom: 2px solid #ff0000;
        }
        .search-bar {
            background-color: #0d0d0d;
            border: 1px solid #ff0000;
            color: #ffffff;
            border-radius: 9999px;
            padding-left: 1.5rem;
            padding-right: 1.5rem;
        }
        .search-bar:focus {
            outline: none;
            box-shadow: 0 0 0 2px #ff0000;
        }
        .iframe-container {
            width: 100%;
            height: calc(100vh - 150px);
            border: 2px solid #ff0000;
            border-radius: 0.5rem;
            overflow: hidden;
        }
        iframe {
            width: 100%;
            height: 100%;
            border: none;
        }
        .settings-button {
            transition: all 0.2s;
        }
        .settings-button:hover {
            transform: scale(1.1);
        }
        .settings-modal {
            background-color: rgba(0, 0, 0, 0.8);
        }
        .modal-content {
            background-color: #0d0d0d;
            border: 2px solid #ff0000;
            max-width: 500px;
            padding: 2rem;
            border-radius: 0.5rem;
        }
        .browser-option {
            transition: all 0.2s;
            cursor: pointer;
        }
        .browser-option:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 6px rgba(255, 0, 0, 0.2);
        }
        .browser-option.selected {
            border: 2px solid #ff0000;
            background-color: #2a0000;
        }
    </style>
</head>
<body class="p-6">
    <div class="container flex flex-col h-screen">
        <!-- Header / Navigation -->
        <header class="header p-4 rounded-t-lg shadow-lg flex items-center justify-between">
            <h1 class="text-3xl font-bold text-red-500">APEX</h1>
            <form action="{{ url_for('proxy_request') }}" method="post" class="w-full mx-4">
                <input type="text" name="url" placeholder="Enter URL or search query..." class="search-bar w-full py-2" required>
            </form>
            <button id="settingsBtn" class="settings-button text-red-500 hover:text-red-400 focus:outline-none">
                <i class="fas fa-cog text-2xl"></i>
            </button>
        </header>

        <!-- Main Content (Iframe) -->
        <main class="flex-grow my-4">
            <div class="iframe-container">
                <iframe id="proxyFrame" src="{{ url_for('home') }}" allowfullscreen></iframe>
            </div>
        </main>
    </div>

    <!-- Settings Modal -->
    <div id="settingsModal" class="settings-modal fixed inset-0 z-50 flex items-center justify-center hidden">
        <div class="modal-content w-full mx-4">
            <div class="flex justify-between items-center mb-6">
                <h2 class="text-2xl font-bold text-red-500">Settings</h2>
                <button id="closeModalBtn" class="text-red-500 hover:text-red-400 text-2xl focus:outline-none">&times;</button>
            </div>
            
            <h3 class="text-lg font-semibold mb-4 text-white">Browser Appearance</h3>
            <div class="grid grid-cols-2 gap-4">
                <div id="chromeOption" class="browser-option p-4 border border-gray-700 rounded-lg text-center selected">
                    <i class="fab fa-chrome text-4xl mb-2 text-red-500"></i>
                    <p>Chrome</p>
                </div>
                <div id="firefoxOption" class="browser-option p-4 border border-gray-700 rounded-lg text-center">
                    <i class="fab fa-firefox-browser text-4xl mb-2 text-red-500"></i>
                    <p>Firefox</p>
                </div>
                <div id="edgeOption" class="browser-option p-4 border border-gray-700 rounded-lg text-center">
                    <i class="fab fa-edge text-4xl mb-2 text-red-500"></i>
                    <p>Edge</p>
                </div>
                <div id="safariOption" class="browser-option p-4 border border-gray-700 rounded-lg text-center">
                    <i class="fab fa-safari text-4xl mb-2 text-red-500"></i>
                    <p>Safari</p>
                </div>
            </div>
        </div>
    </div>

    <script>
        const settingsBtn = document.getElementById('settingsBtn');
        const settingsModal = document.getElementById('settingsModal');
        const closeModalBtn = document.getElementById('closeModalBtn');
        const proxyFrame = document.getElementById('proxyFrame');
        const browserOptions = document.querySelectorAll('.browser-option');

        // Toggle modal visibility
        settingsBtn.addEventListener('click', () => {
            settingsModal.classList.remove('hidden');
        });
        closeModalBtn.addEventListener('click', () => {
            settingsModal.classList.add('hidden');
        });

        // Simple visual selection for "browser change"
        browserOptions.forEach(option => {
            option.addEventListener('click', () => {
                browserOptions.forEach(opt => opt.classList.remove('selected'));
                option.classList.add('selected');
            });
        });
    </script>
</body>
</html>
"""

# --- Initial homepage route ---
@app.route('/')
def home():
    """Renders the main page with the embedded HTML template."""
    return render_template_string(HTML_TEMPLATE)

# --- Proxy request handler ---
@app.route('/proxy', methods=['POST'])
def proxy_request():
    """
    Handles the POST request from the search bar.
    It determines if the input is a URL or a search query and redirects accordingly.
    """
    url_input = request.form.get('url', '').strip()
    
    # Check if the input is a valid URL
    if re.match(r'^https?://', url_input):
        return redirect(url_for('serve_proxy', url=url_input))
    elif '.' in url_input:
        # A simple check for a domain name (e.g., google.com)
        url = f'http://{url_input}'
        return redirect(url_for('serve_proxy', url=url))
    else:
        # Assume it's a search query and redirect to Google
        search_query = quote_plus(url_input)
        search_url = f'https://www.google.com/search?q={search_query}'
        return redirect(url_for('serve_proxy', url=search_url))

def rewrite_html(content, target_url):
    """
    Parses the HTML and rewrites all URLs to be proxied.
    """
    soup = BeautifulSoup(content, 'lxml')
    
    # Define tags and attributes to rewrite
    tags_to_rewrite = {
        'a': 'href',
        'link': 'href',
        'script': 'src',
        'img': 'src',
        'source': 'src',
        'iframe': 'src',
        'form': 'action',
    }
    
    parsed_url = urlparse(target_url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

    for tag, attr in tags_to_rewrite.items():
        for element in soup.find_all(tag, **{attr: True}):
            url = element.get(attr)
            if url and not url.startswith('http'):
                abs_url = urljoin(base_url, url)
                element[attr] = url_for('serve_proxy', url=abs_url)

    # Rewrite style URLs within the style tags
    for style_tag in soup.find_all('style'):
        style_content = style_tag.string
        if style_content:
            style_content = re.sub(
                r'url\((["\']?)(.*?)\1\)',
                lambda match: f'url({match.group(1)}{url_for("serve_proxy", url=urljoin(base_url, match.group(2)))}{match.group(1)})',
                style_content
            )
            style_tag.string = style_content
            
    return str(soup)

# --- Main proxy serving route ---
@app.route('/serve_proxy', methods=['GET'])
def serve_proxy():
    """
    Fetches the content from the target URL, rewrites it, and serves it to the user.
    This is the more robust version.
    """
    target_url = request.args.get('url')
    if not target_url:
        return "Error: No URL provided", 400

    print(f"Proxying request for: {target_url}")

    try:
        # Create a new headers dictionary, excluding 'Accept-Encoding'
        headers = {key: value for key, value in request.headers.items() if key != 'Accept-Encoding'}

        # Make the request with the modified headers
        response = requests.get(target_url, headers=headers, timeout=10)
        
        # Detect encoding and decode the content
        encoding = chardet.detect(response.content)['encoding'] or 'utf-8'
        content = response.content.decode(encoding, errors='ignore')
        
        # Rewrite the content
        rewritten_content = rewrite_html(content, target_url)

        # Create a Flask response object with the modified content
        flask_response = Response(rewritten_content, status=response.status_code)

        # Copy over useful headers, excluding Hop-by-Hop headers and security headers
        excluded_headers = ['connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization', 'te', 'trailers', 'transfer-encoding', 'upgrade', 'x-frame-options', 'content-security-policy']
        for key, value in response.headers.items():
            if key.lower() not in excluded_headers:
                flask_response.headers[key] = value

        # Set a Content-Security-Policy to allow content from the target URL
        # We need to relax the CSP to allow the rewritten content to load.
        flask_response.headers['Content-Security-Policy'] = "default-src 'self' 'unsafe-inline' 'unsafe-eval' data:; connect-src *; style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; img-src * data:; script-src 'self' 'unsafe-inline' 'unsafe-eval';"
        flask_response.headers['Content-Type'] = 'text/html; charset=utf-8'

        return flask_response

    except requests.exceptions.RequestException as e:
        print(f"Proxy Error: {e}")
        return f"<h1>Proxy Error</h1><p>Could not connect to the requested URL: {target_url}</p><p>Details: {e}</p>", 502
