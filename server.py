import http.server
import socketserver
from socketserver import ThreadingMixIn
import os
from urllib.parse import urlparse, parse_qs, unquote
import os.path, time
from operator import itemgetter
from pathlib import Path
import sqlite3
import hashlib
from datetime import datetime, timedelta
import calendar
import json
import csv
import io
import shutil
import zipfile
import logging
from logging.handlers import RotatingFileHandler
import traceback

PORT = 8000

# Base content directory
CONTENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'content')

# Directory where markdown files are stored
PAGES_DIR = os.path.join(CONTENT_DIR, 'pages')

# Directory where message files are stored
MESSAGES_DIR = os.path.join(CONTENT_DIR, 'messages')

# Directory for static files
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')

# Schedule database file
SCHEDULE_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schedule.db')

# Add these constants at the top of the file
SURGERY_USERNAME = "2466"
SURGERY_PASSWORD = "2466"

# Configure logging
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server.log')
logging.basicConfig(
    handlers=[RotatingFileHandler(LOG_FILE, maxBytes=1024*1024, backupCount=5)],
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Function to parse front matter
def parse_front_matter(content):
    try:
        # Ensure content is properly decoded
        if isinstance(content, bytes):
            content = content.decode('utf-8-sig')  # Handle BOM if present
            
        lines = content.split('\n')
        if lines[0].strip() == '---':
            try:
                end = lines[1:].index('---') + 1
                front_matter = lines[1:end]
                body = '\n'.join(lines[end+1:])
                metadata = {}
                current_key = None
                current_list = []
                
                for line in front_matter:
                    line = line.strip()
                    if not line:  # Skip empty lines
                        continue
                        
                    if ':' in line and not line.startswith('-'):
                        # Handle key-value pairs
                        key, value = [x.strip() for x in line.split(':', 1)]
                        if value:  # If there's a value on the same line
                            metadata[key] = value.strip('"').strip("'")  # Remove quotes if present
                        else:  # If it's a key for a list
                            current_key = key
                            current_list = []
                            metadata[current_key] = current_list
                    elif line.startswith('-') and current_key:
                        # Handle list items
                        value = line[1:].strip().strip('"').strip("'")
                        if current_key == 'classification':
                            if '>' in value:  # Format: "MainCategory > SubCategory"
                                main_cat, sub_cat = [x.strip() for x in value.split('>')]
                                if 'classifications' not in metadata:
                                    metadata['classifications'] = {}
                                if main_cat not in metadata['classifications']:
                                    metadata['classifications'][main_cat] = []
                                metadata['classifications'][main_cat].append(sub_cat)
                            else:
                                # Handle single category without subcategory
                                if 'classifications' not in metadata:
                                    metadata['classifications'] = {}
                                if value not in metadata['classifications']:
                                    metadata['classifications'][value] = []
                        else:
                            current_list.append(value)
                
                return metadata, body
            except ValueError:
                return {}, content
    except Exception as e:
        print(f"Error parsing front matter: {str(e)}")
        return {}, content
    return {}, content

# Basic Markdown to HTML converter
def markdown_to_html(markdown_text):
    toc = []
    html = []
    header_count = 0  # Counter for headers
    
    for line in markdown_text.split('\n'):
        if line.startswith('# ') or line.startswith('## ') or line.startswith('### '):
            header_count += 1  # Increment counter for each header
            
        if line.startswith('# '):
            # H1 header
            title = line[2:].strip()
            anchor = title.lower()
            toc.append(f"<li><a href='#{anchor}'>{title}</a></li>")
            html.append(f"<h1 id='{anchor}'>{title}</h1>\n")
        elif line.startswith('## '):
            # H2 header
            title = line[3:].strip()
            anchor = title.lower()
            toc.append(f"<li style='margin-left: 20px'><a href='#{anchor}'>{title}</a></li>")
            html.append(f"<h2 id='{anchor}'>{title}</h2>\n")
        elif line.startswith('### '):
            # H3 header
            title = line[4:].strip()
            anchor = title.lower()
            toc.append(f"<li style='margin-left: 40px'><a href='#{anchor}'>{title}</a></li>")
            html.append(f"<h3 id='{anchor}'>{title}</h3>\n")
        elif line.startswith('!['):
            # Handle image syntax: ![alt text](image_url)
            try:
                alt_text = line[2:].split('](')[0]
                image_url = line.split('](')[1].strip(')')
                html.append(f'<img src="{image_url}" alt="{alt_text}" style="cursor: pointer;" onclick="window.open(this.src)">\n')
            except:
                html.append(f"<p>{line}</p>\n")
        elif '[file:' in line:
            # Handle file attachment syntax: [file:filename](path/to/file)
            try:
                file_name = line.split('[file:')[1].split('](')[0]
                file_path = line.split('](')[1].strip(')')
                html.append(f'<p class="attachment"><a href="{file_path}" target="_blank"><img src="/static/images/file-icon.png" class="file-icon" alt="File">{file_name}</a></p>\n')
            except:
                html.append(f"<p>{line}</p>\n")
        elif '[' in line and '](' in line:
            # Handle normal links: [text](url)
            try:
                parts = line.split('[')
                html_line = parts[0]
                for part in parts[1:]:
                    if '](' in part:
                        link_text = part.split('](')[0]
                        link_url = part.split('](')[1].split(')')[0]
                        remaining = ')'.join(part.split('](')[1].split(')')[1:])
                        if link_url.startswith('http'):
                            html_line += f'<a href="{link_url}" target="_blank">{link_text}</a>{remaining}'
                        else:
                            html_line += f'<a href="{link_url}">{link_text}</a>{remaining}'
                    else:
                        html_line += '[' + part
                html.append(f"<p>{html_line}</p>\n")
            except:
                html.append(f"<p>{line}</p>\n")
        else:
            html.append(f"<p>{line}</p>\n")
    
    # Only add TOC if there are at least 3 headers
    if toc and header_count >= 3:
        toc_html = "<div class='table-of-contents'>\n<h2>Table of Contents</h2>\n<ul>\n"
        toc_html += "\n".join(toc)
        toc_html += "\n</ul>\n</div>\n"
        html.insert(0, toc_html)  # Insert at the beginning of content
    
    return "\n".join(html)

def read_template(template_name):
    """Read and return the content of a template file."""
    template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates', template_name)
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"Error reading template {template_name}: {str(e)}")
        return ""

def render_template(template_content, **kwargs):
    """Replace placeholders in template with actual values."""
    # Handle if conditions first
    if '{% if' in template_content:
        while '{% if' in template_content:
            start = template_content.find('{% if')
            end = template_content.find('{% endif %}') + 9
            if_block = template_content[start:end]
            condition = if_block[if_block.find('if')+2:if_block.find('%}')].strip()
            content = if_block[if_block.find('%}')+2:if_block.find('{% endif %}')]
            
            # Evaluate condition
            try:
                var_name = condition.split()[0]
                if '!=' in condition:
                    var_name = condition.split('!=')[0].strip()
                    compare_value = condition.split('!=')[1].strip().strip("'").strip('"')
                    should_show = kwargs.get(var_name) and kwargs[var_name] != compare_value
                else:
                    should_show = kwargs.get(var_name)
                
                template_content = template_content.replace(if_block, content if should_show else '')
            except:
                template_content = template_content.replace(if_block, '')

    # Handle for loops
    while '{% for' in template_content:
        start = template_content.find('{% for')
        end = template_content.find('{% endfor %}') + 12  # Changed to 12 to include full endfor tag
        loop_block = template_content[start:end]
        
        # Parse loop parameters
        loop_def = loop_block[loop_block.find('for')+3:loop_block.find('%}')].strip()
        item_name = loop_def.split()[0]
        collection_name = loop_def.split()[-1]
        
        # Get loop content template
        loop_content = loop_block[loop_block.find('%}')+2:loop_block.find('{% endfor %}')]
        
        # Get the collection from kwargs
        collection = kwargs.get(collection_name, [])
        
        # Generate content for each item
        generated_content = []
        for item in collection:
            item_content = loop_content
            if isinstance(item, dict):
                for key, value in item.items():
                    placeholder = '{{ ' + f"{item_name}.{key}" + ' }}'
                    item_content = item_content.replace(placeholder, str(value))
            else:
                placeholder = '{{ ' + item_name + ' }}'
                item_content = item_content.replace(placeholder, str(item))
            generated_content.append(item_content)
        
        # Replace the entire loop block with generated content
        template_content = template_content.replace(loop_block, ''.join(generated_content))

    # Handle simple placeholders
    for key, value in kwargs.items():
        placeholder = '{{ ' + key + ' }}'
        if isinstance(value, str):
            # Don't escape HTML in template content
            template_content = template_content.replace(placeholder, value)
        else:
            template_content = template_content.replace(placeholder, str(value))
    
    # Clean up any remaining template tags
    template_content = template_content.replace('{% endfor } %}', '')
    template_content = template_content.replace('{% endfor %}', '')
    template_content = template_content.replace('%}', '')
    
    return template_content

# Add this function before the IntranetHandler class
def collect_classifications():
    classifications_hierarchy = {}
    for filename in os.listdir(PAGES_DIR):
        if filename.endswith('.md'):
            filepath = os.path.join(PAGES_DIR, filename)
            try:
                content = None
                for encoding in ['utf-8-sig', 'utf-8', 'gb18030']:
                    try:
                        with open(filepath, 'r', encoding=encoding) as f:
                            content = f.read()
                            metadata, _ = parse_front_matter(content)
                            if 'classifications' in metadata:
                                for main_cat, sub_cats in metadata['classifications'].items():
                                    if main_cat not in classifications_hierarchy:
                                        classifications_hierarchy[main_cat] = set()
                                    if sub_cats:  # If there are subcategories
                                        classifications_hierarchy[main_cat].update(sub_cats)
                                    else:  # If it's a standalone category
                                        classifications_hierarchy[main_cat] = set()
                            break
                    except UnicodeDecodeError:
                        continue
                if content is None:
                    print(f"Failed to decode file {filename} with any encoding")
                    continue
            except Exception as e:
                print(f"Error reading file {filename}: {str(e)}")
                continue
    return classifications_hierarchy

def get_related_pages(classifications, current_page):
    related = []
    for filename in os.listdir(PAGES_DIR):
        if filename.endswith('.md') and filename != current_page:
            filepath = os.path.join(PAGES_DIR, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    metadata, _ = parse_front_matter(content)
                    if 'classifications' in metadata:
                        # If there's any overlap in classifications, add to related
                        if any(cat in classifications for cat in metadata['classifications']):
                            title = metadata.get('title', filename.replace('.md', ''))
                            related.append({
                                'title': title,
                                'filename': filename.replace('.md', '')
                            })
            except Exception as e:
                print(f"Error reading related file {filename}: {str(e)}")
                continue
    return related

def track_page_versions(filepath):
    # Store page versions with timestamps
    # Allow viewing previous versions
    pass

def get_file_mtime(filepath):
    return os.path.getmtime(filepath)

# Add this new function to load messages
def load_messages():
    messages = []
    if os.path.exists(MESSAGES_DIR):
        for filename in os.listdir(MESSAGES_DIR):
            if filename.endswith('.txt'):
                filepath = os.path.join(MESSAGES_DIR, filename)
                try:
                    for encoding in ['utf-8-sig', 'utf-8', 'gb18030']:
                        try:
                            with open(filepath, 'r', encoding=encoding) as f:
                                message = f.read().strip()
                                if message:  # Only add non-empty messages
                                    messages.append(message)
                            break
                        except UnicodeDecodeError:
                            continue
                except Exception as e:
                    print(f"Error reading message file {filename}: {str(e)}")
                    continue
    return messages if messages else ["Welcome to our Intranet!"]  # Default message if no files found

# Add this function to initialize the schedule database
def init_schedule_db():
    conn = sqlite3.connect(SCHEDULE_DB)
    cursor = conn.cursor()
    
    # Create Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Users (
            UserID INTEGER PRIMARY KEY AUTOINCREMENT,
            Username TEXT UNIQUE NOT NULL,
            Password TEXT NOT NULL
        )
    ''')
    
    # Create Schedule table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Schedule (
            ScheduleID INTEGER PRIMARY KEY AUTOINCREMENT,
            UserID INTEGER NOT NULL,
            Title TEXT NOT NULL,
            Description TEXT,
            DateTime TEXT NOT NULL,
            FOREIGN KEY (UserID) REFERENCES Users(UserID)
        )
    ''')
    
    # Create Surgery Schedule table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS SurgerySchedule (
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            Department TEXT NOT NULL,
            Date TEXT NOT NULL,
            BedNumber TEXT NOT NULL,
            PatientName TEXT NOT NULL,
            Gender TEXT NOT NULL,
            Age INTEGER NOT NULL,
            HospitalNumber TEXT NOT NULL,
            Diagnosis TEXT NOT NULL,
            Operation TEXT NOT NULL,
            MainSurgeon TEXT NOT NULL,
            Assistant TEXT NOT NULL,
            AnesthesiaDoctor TEXT NOT NULL,
            AnesthesiaType TEXT NOT NULL,
            PreOpPrep TEXT,
            OperationOrder INTEGER NOT NULL,
            Creator TEXT NOT NULL,
            Editor TEXT NOT NULL,
            CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UpdatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

class IntranetHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urlparse(self.path)
        path = unquote(parsed_path.path)
        query = parse_qs(parsed_path.query)

        if path == '/':
            self.handle_index()
        elif path == '/schedule':
            # First check if we should show login or schedule page
            self.handle_schedule_page()
        elif path == '/schedule/login':
            # Show the login page
            self.send_file('templates/login.html')
        elif path == '/api/schedules':
            self.handle_get_schedules()
        elif path.startswith('/classification/'):
            # Handle classification routes
            parts = path.split('/')[2:]  # Split path and remove empty first element and 'classification'
            if len(parts) == 2:  # Has both category and subcategory
                self.handle_classification(parts[0], parts[1])
            elif len(parts) == 1:  # Has only category
                self.handle_classification(parts[0])
            else:
                self.send_error(404, "Invalid classification path")
        elif path == '/all-articles':
            self.handle_all_articles()
        elif path.startswith('/page/'):
            page_name = path.split('/page/')[-1]
            self.handle_page(page_name)
        elif path.startswith('/search'):
            search_query = query.get('q', [''])[0]
            self.handle_search(search_query)
        elif path == '/surgery':
            # Direct access to surgery page without login
            self.handle_surgery_page()
        elif path == '/api/surgeries':
            self.handle_get_surgeries()
        elif path == '/api/surgeries/export':
            self.handle_export_surgeries()
        elif path == '/api/surgeries/history':
            self.handle_get_history()
        else:
            # Let SimpleHTTPRequestHandler handle static files
            super().do_GET()

    def handle_index(self):
        parsed_path = urlparse(self.path)
        query = parse_qs(parsed_path.query)
        selected_category = query.get('category', [None])[0]
        selected_subcategory = query.get('subcategory', [None])[0]
        show_all = query.get('view', [''])[0] == 'all'
        
        if selected_category:
            selected_category = unquote(selected_category)
        if selected_subcategory:
            selected_subcategory = unquote(selected_subcategory)
        
        # Get classifications hierarchy
        classifications_hierarchy = collect_classifications()

        # Generate menu HTML with Home link first
        menu_html = ['<li><a href="/">Home</a></li>']
        
        # Add menu items for each category
        for main_cat, sub_cats in sorted(classifications_hierarchy.items()):
            # Determine if this category is active
            is_active = main_cat == selected_category
            active_class = ' active' if is_active else ''
            
            # Create dropdown menu
            sub_menu = []
            for sub_cat in sorted(sub_cats):
                # Determine if this subcategory is active
                sub_active_class = ' active' if sub_cat == selected_subcategory else ''
                sub_menu.append(
                    f'<li><a href="/classification/{main_cat}/{sub_cat}" '
                    f'class="{sub_active_class}">{sub_cat}</a></li>'
                )
            
            # Add the category with its dropdown
            menu_html.append(f'''
                <li class="dropdown">
                    <a href="/classification/{main_cat}" class="dropbtn{active_class}">{main_cat}</a>
                    <ul class="dropdown-content">
                        {' '.join(sub_menu)}
                    </ul>
                </li>
            ''')

        # Collect all pages with their modification times
        all_pages_data = []
        if os.path.exists(PAGES_DIR):
            for filename in os.listdir(PAGES_DIR):
                if filename.endswith('.md'):
                    filepath = os.path.join(PAGES_DIR, filename)
                    try:
                        content = None
                        for encoding in ['utf-8-sig', 'utf-8', 'gb18030']:
                            try:
                                with open(filepath, 'r', encoding=encoding) as f:
                                    content = f.read()
                                    metadata, _ = parse_front_matter(content)
                                    title = metadata.get('title', filename.replace('.md', ''))
                                    
                                    # Format classifications
                                    if 'classifications' in metadata:
                                        formatted_classifications = []
                                        for main_cat, sub_cats in metadata['classifications'].items():
                                            if sub_cats:
                                                for sub_cat in sub_cats:
                                                    formatted_classifications.append(f"{main_cat} > {sub_cat}")
                                            else:
                                                formatted_classifications.append(main_cat)
                                        classification_text = ', '.join(formatted_classifications)
                                    else:
                                        classification_text = 'General'
                                    
                                    base_filename = os.path.splitext(filename)[0]
                                    all_pages_data.append({
                                        'title': title,
                                        'classification': classification_text,
                                        'filename': base_filename,
                                        'mtime': get_file_mtime(filepath)
                                    })
                                    break
                            except UnicodeDecodeError:
                                continue
                    except Exception as e:
                        print(f"Error reading file {filename}: {str(e)}")
                        continue

        # Sort pages by modification time (newest first)
        all_pages_data.sort(key=itemgetter('mtime'), reverse=True)
        
        # Get recent pages (top 10)
        recent_pages = all_pages_data[:10]
        
        # Load messages from files
        messages = load_messages()

        # Get footer content
        footer_content = read_template('footer.html')
        
        # Read and render the template
        template = read_template('index.html')
        html_content = render_template(template,
            title=f"Intranet Site{' - ' + selected_category if selected_category else ''}",
            menu_html=''.join(menu_html),
            recent_pages=recent_pages,
            pages=all_pages_data if show_all else [],
            show_all_pages=show_all,
            messages=messages,
            footer=footer_content
        )
        
        self.respond_with_html(html_content)

    def handle_page(self, name):
        # Get classifications hierarchy
        classifications_hierarchy = collect_classifications()
        
        # Generate menu HTML with Home link first
        menu_html = ['<li><a href="/">Home</a></li>']
        for main_cat, sub_cats in sorted(classifications_hierarchy.items()):
            sub_menu = ''.join([
                f'<li><a href="/?category={main_cat}&subcategory={sub_cat}">{sub_cat}</a></li>'
                for sub_cat in sorted(sub_cats)
            ])
            menu_html.append(f'''
                <li class="dropdown">
                    <a href="/?category={main_cat}" class="dropbtn">{main_cat}</a>
                    <ul class="dropdown-content">
                        {sub_menu}
                    </ul>
                </li>
            ''')

        # Handle the current page
        filename = f"{name}.md"
        filepath = os.path.join(PAGES_DIR, filename)
        if not os.path.exists(filepath):
            self.send_error(404, "Page Not Found")
            return
            
        try:
            # Try different encodings
            content = None
            for encoding in ['utf-8-sig', 'utf-8', 'gb18030']:
                try:
                    with open(filepath, 'r', encoding=encoding) as f:
                        content = f.read()
                        break  # If successful, break the encoding loop
                except UnicodeDecodeError:
                    continue
            
            if content is None:
                raise UnicodeDecodeError("Failed to decode file with any encoding")
                
            metadata, body = parse_front_matter(content)
            html_content = markdown_to_html(body)
            
            # Get title from metadata or use filename
            title = metadata.get('title', name)
            
            # Format classifications
            classification_text = ""
            if 'classifications' in metadata:
                formatted_classifications = []
                for main_cat, sub_cats in metadata['classifications'].items():
                    if sub_cats:  # If there are subcategories
                        for sub_cat in sub_cats:
                            formatted_classifications.append(f"{main_cat} > {sub_cat}")
                    else:  # If it's a standalone category
                        formatted_classifications.append(main_cat)
                classification_text = ', '.join(formatted_classifications)
            else:
                classification_text = 'General'
            
            # Get footer content
            footer_content = read_template('footer.html')
            
            # Read and render the template
            template = read_template('page.html')
            html_content = render_template(template,
                title=title,
                menu_html=''.join(menu_html),
                classification=classification_text,
                content=html_content,
                footer=footer_content  # Add footer content
            )
            
            self.respond_with_html(html_content)
        except Exception as e:
            print(f"Error processing file {filename}: {str(e)}")
            self.send_error(500, f"Error processing file: {str(e)}")

    def handle_search(self, query):
        if not query:
            self.handle_index()
            return

        results = []
        for filename in os.listdir(PAGES_DIR):
            if filename.endswith('.md'):
                filepath = os.path.join(PAGES_DIR, filename)
                try:
                    content = None
                    for encoding in ['utf-8-sig', 'utf-8', 'gb18030']:
                        try:
                            with open(filepath, 'r', encoding=encoding) as f:
                                content = f.read()
                                metadata, body = parse_front_matter(content)
                                
                                # Search in title, content, and classifications
                                title = metadata.get('title', filename.replace('.md', ''))
                                if (query.lower() in title.lower() or
                                    query.lower() in body.lower() or
                                    query.lower() in str(metadata.get('classifications', '')).lower()):
                                    
                                    # Create a content snippet around the matched text
                                    query_pos = body.lower().find(query.lower())
                                    start = max(0, query_pos - 100)
                                    end = min(len(body), query_pos + 100)
                                    snippet = '...' + body[start:end] + '...' if query_pos != -1 else body[:200] + '...'
                                    
                                    # Format classifications
                                    if 'classifications' in metadata:
                                        formatted_classifications = []
                                        for main_cat, sub_cats in metadata['classifications'].items():
                                            if sub_cats:
                                                for sub_cat in sub_cats:
                                                    formatted_classifications.append(f"{main_cat} > {sub_cat}")
                                            else:
                                                formatted_classifications.append(main_cat)
                                        classification_text = ', '.join(formatted_classifications)
                                    else:
                                        classification_text = 'General'
                                    
                                    results.append({
                                        'title': title,
                                        'filename': filename.replace('.md', ''),
                                        'snippet': snippet,
                                        'classification': classification_text
                                    })
                                break
                        except UnicodeDecodeError:
                            continue
                except Exception as e:
                    print(f"Error reading file {filename}: {str(e)}")
                    continue

        # Generate menu HTML for navigation
        classifications_hierarchy = collect_classifications()
        menu_html = ['<li><a href="/">Home</a></li>']
        for main_cat, sub_cats in sorted(classifications_hierarchy.items()):
            sub_menu = ''.join([
                f'<li><a href="/?category={main_cat}&subcategory={sub_cat}">{sub_cat}</a></li>'
                for sub_cat in sorted(sub_cats)
            ])
            menu_html.append(f'''
                <li class="dropdown">
                    <a href="/?category={main_cat}" class="dropbtn">{main_cat}</a>
                    <ul class="dropdown-content">
                        {sub_menu}
                    </ul>
                </li>
            ''')

        # Get footer content
        footer_content = read_template('footer.html')
        
        # Read and render the template
        template = read_template('search.html')
        html_content = render_template(template, 
            query=query,
            results=results,
            result_count=len(results),
            menu_html=''.join(menu_html),
            footer=footer_content  # Add footer content
        )
        self.respond_with_html(html_content)

    def handle_all_articles(self):
        # Get classifications hierarchy for menu
        classifications_hierarchy = collect_classifications()
        
        # Generate menu HTML
        menu_html = ['<li><a href="/">Home</a></li>']
        for main_cat, sub_cats in sorted(classifications_hierarchy.items()):
            sub_menu = []
            for sub_cat in sorted(sub_cats):
                sub_menu.append(
                    f'<li><a href="/?category={main_cat}&subcategory={sub_cat}">{sub_cat}</a></li>'
                )
            menu_html.append(f'''
                <li class="dropdown">
                    <a href="/?category={main_cat}" class="dropbtn">{main_cat}</a>
                    <ul class="dropdown-content">
                        {' '.join(sub_menu)}
                    </ul>
                </li>
            ''')

        # Collect all pages with their modification times
        all_pages_data = []
        for filename in os.listdir(PAGES_DIR):
            if filename.endswith('.md'):
                filepath = os.path.join(PAGES_DIR, filename)
                try:
                    content = None
                    for encoding in ['utf-8-sig', 'utf-8', 'gb18030']:
                        try:
                            with open(filepath, 'r', encoding=encoding) as f:
                                content = f.read()
                                metadata, _ = parse_front_matter(content)
                                title = metadata.get('title', filename.replace('.md', ''))
                                
                                # Format classifications
                                if 'classifications' in metadata:
                                    formatted_classifications = []
                                    for main_cat, sub_cats in metadata['classifications'].items():
                                        if sub_cats:
                                            for sub_cat in sub_cats:
                                                formatted_classifications.append(f"{main_cat} > {sub_cat}")
                                        else:
                                            formatted_classifications.append(main_cat)
                                    classification_text = ', '.join(formatted_classifications)
                                else:
                                    classification_text = 'General'
                                
                                base_filename = os.path.splitext(filename)[0]
                                all_pages_data.append({
                                    'title': title,
                                    'classification': classification_text,
                                    'filename': base_filename,
                                    'mtime': get_file_mtime(filepath)
                                })
                                break
                        except UnicodeDecodeError:
                            continue
                except Exception as e:
                    print(f"Error reading file {filename}: {str(e)}")
                    continue

        # Sort pages by modification time (newest first)
        all_pages_data.sort(key=itemgetter('mtime'), reverse=True)
        
        # Get footer content
        footer_content = read_template('footer.html')
        
        # Read and render the template
        template = read_template('all_articles.html')
        html_content = render_template(template,
            title="Intranet Site",
            menu_html=''.join(menu_html),
            pages=all_pages_data,
            footer=footer_content
        )
        
        self.respond_with_html(html_content)

    def handle_classification(self, category, subcategory=None):
        # Get classifications hierarchy for menu
        classifications_hierarchy = collect_classifications()
        
        # Generate menu HTML
        menu_html = ['<li><a href="/">Home</a></li>']
        for main_cat, sub_cats in sorted(classifications_hierarchy.items()):
            is_active = main_cat == category
            active_class = ' active' if is_active else ''
            
            sub_menu = []
            for sub_cat in sorted(sub_cats):
                sub_active_class = ' active' if sub_cat == subcategory else ''
                sub_menu.append(
                    f'<li><a href="/classification/{main_cat}/{sub_cat}" '
                    f'class="{sub_active_class}">{sub_cat}</a></li>'
                )
            
            menu_html.append(f'''
                <li class="dropdown">
                    <a href="/classification/{main_cat}" class="dropbtn{active_class}">{main_cat}</a>
                    <ul class="dropdown-content">
                        {' '.join(sub_menu)}
                    </ul>
                </li>
            ''')

        # Collect filtered pages
        filtered_pages = []
        for filename in os.listdir(PAGES_DIR):
            if filename.endswith('.md'):
                filepath = os.path.join(PAGES_DIR, filename)
                try:
                    content = None
                    for encoding in ['utf-8-sig', 'utf-8', 'gb18030']:
                        try:
                            with open(filepath, 'r', encoding=encoding) as f:
                                content = f.read()
                                metadata, _ = parse_front_matter(content)
                                
                                # Check if page matches the category/subcategory filter
                                if 'classifications' in metadata:
                                    if subcategory:
                                        # Check for specific subcategory
                                        if (category in metadata['classifications'] and 
                                            subcategory in metadata['classifications'][category]):
                                            title = metadata.get('title', filename.replace('.md', ''))
                                            
                                            # Format classifications
                                            formatted_classifications = []
                                            for main_cat, sub_cats in metadata['classifications'].items():
                                                if sub_cats:
                                                    for sub_cat in sub_cats:
                                                        formatted_classifications.append(f"{main_cat} > {sub_cat}")
                                                else:
                                                    formatted_classifications.append(main_cat)
                                            classification_text = ', '.join(formatted_classifications)
                                            
                                            filtered_pages.append({
                                                'title': title,
                                                'classification': classification_text,
                                                'filename': filename.replace('.md', ''),
                                                'mtime': get_file_mtime(filepath)
                                            })
                                    else:
                                        # Check for main category only
                                        if category in metadata['classifications']:
                                            title = metadata.get('title', filename.replace('.md', ''))
                                            
                                            # Format classifications
                                            formatted_classifications = []
                                            for main_cat, sub_cats in metadata['classifications'].items():
                                                if sub_cats:
                                                    for sub_cat in sub_cats:
                                                        formatted_classifications.append(f"{main_cat} > {sub_cat}")
                                                else:
                                                    formatted_classifications.append(main_cat)
                                            classification_text = ', '.join(formatted_classifications)
                                            
                                            filtered_pages.append({
                                                'title': title,
                                                'classification': classification_text,
                                                'filename': filename.replace('.md', ''),
                                                'mtime': get_file_mtime(filepath)
                                            })
                            break
                        except UnicodeDecodeError:
                            continue
                except Exception as e:
                    print(f"Error reading file {filename}: {str(e)}")
                    continue

        # Sort pages by modification time (newest first)
        filtered_pages.sort(key=itemgetter('mtime'), reverse=True)
        
        # Get footer content
        footer_content = read_template('footer.html')
        
        # Read and render the template
        template = read_template('classification.html')
        html_content = render_template(template,
            title="Intranet Site",
            category=category,
            subcategory_title=f" > {subcategory}" if subcategory else "",
            menu_html=''.join(menu_html),
            filtered_pages=filtered_pages,
            footer=footer_content
        )
        
        self.respond_with_html(html_content)

    def handle_schedule_login(self):
        logger.info("Schedule login attempt")
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        data = parse_qs(post_data)
        
        username = data.get('username', [''])[0]
        password = data.get('password', [''])[0]
        
        if not username or not password:
            self.send_json({'success': False, 'message': 'Username and password required'})
            return
        
        conn = sqlite3.connect(SCHEDULE_DB)
        cursor = conn.cursor()
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        
        cursor.execute(
            'SELECT UserID FROM Users WHERE Username=? AND Password=?',
            (username, hashed_password)
        )
        user = cursor.fetchone()
        conn.close()
        
        if user:
            self.send_json({'success': True, 'user_id': user[0]})
        else:
            self.send_json({'success': False, 'message': 'Invalid credentials'})

    def handle_schedule_register(self):
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length).decode('utf-8')
            data = parse_qs(post_data)
            
            username = data.get('username', [''])[0]
            password = data.get('password', [''])[0]
            
            if not username or not password:
                self.send_json({'success': False, 'message': '用户名和密码不能为空'})
                return
            
            # Initialize database connection
            conn = sqlite3.connect(SCHEDULE_DB)
            cursor = conn.cursor()
            
            try:
                # Check if username already exists
                cursor.execute('SELECT UserID FROM Users WHERE Username=?', (username,))
                if cursor.fetchone():
                    self.send_json({'success': False, 'message': '用户名已存在'})
                    return
                
                # Hash the password
                hashed_password = hashlib.sha256(password.encode()).hexdigest()
                
                # Insert new user
                cursor.execute(
                    "INSERT INTO Users (Username, Password) VALUES (?, ?)",
                    (username, hashed_password))
                conn.commit()
                self.send_json({'success': True, 'message': '注册成功'})
                
            except sqlite3.Error as e:
                print(f"Database error: {e}")
                self.send_json({'success': False, 'message': '数据库错误'})
            finally:
                conn.close()
                
        except Exception as e:
            print(f"Registration error: {e}")
            self.send_json({'success': False, 'message': f'注册失败: {str(e)}'})

    def handle_get_schedules(self):
        # Get query parameters
        params = parse_qs(urlparse(self.path).query)
        user_id = params.get('user_id', [''])[0]
        view_type = params.get('view', ['day'])[0]
        date_str = params.get('date', [datetime.now().strftime('%Y-%m-%d')])[0]

        if not user_id:
            self.send_json({'success': False, 'message': 'Not logged in'})
            return

        # Calculate date range
        selected_date = datetime.strptime(date_str, '%Y-%m-%d')
        if view_type == 'day':
            start_date = selected_date
            end_date = selected_date + timedelta(days=1)
        elif view_type == 'week':
            start_date = selected_date - timedelta(days=selected_date.weekday())
            end_date = start_date + timedelta(days=7)
        else:  # month
            start_date = selected_date.replace(day=1)
            _, last_day = calendar.monthrange(selected_date.year, selected_date.month)
            end_date = start_date.replace(day=last_day)

        # Get schedules from database
        conn = sqlite3.connect(SCHEDULE_DB)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT ScheduleID, Title, Description, DateTime 
            FROM Schedule 
            WHERE UserID=? AND DateTime BETWEEN ? AND ?
            ORDER BY DateTime
        ''', (user_id, start_date.strftime('%Y-%m-%d'),
              end_date.strftime('%Y-%m-%d')))
        
        schedules = [{
            'id': row[0],
            'title': row[1],
            'description': row[2],
            'datetime': row[3]
        } for row in cursor.fetchall()]
        
        conn.close()
        self.send_json({'success': True, 'schedules': schedules})

    def handle_add_schedule(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        data = parse_qs(post_data)
        
        user_id = data.get('user_id', [''])[0]
        title = data.get('title', [''])[0]
        description = data.get('description', [''])[0]
        datetime_str = data.get('datetime', [''])[0]
        
        if not all([user_id, title, datetime_str]):
            self.send_json({'success': False, 'message': 'Required fields cannot be empty'})
            return
        
        conn = sqlite3.connect(SCHEDULE_DB)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO Schedule (UserID, Title, Description, DateTime)
                VALUES (?, ?, ?, ?)
            ''', (user_id, title, description, datetime_str))
            
            conn.commit()
            self.send_json({'success': True, 'message': 'Schedule added successfully'})
            
        except Exception as e:
            self.send_json({'success': False, 'message': str(e)})
        finally:
            conn.close()

    def handle_edit_schedule(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        data = parse_qs(post_data)
        
        schedule_id = data.get('schedule_id', [''])[0]
        user_id = data.get('user_id', [''])[0]
        title = data.get('title', [''])[0]
        description = data.get('description', [''])[0]
        datetime_str = data.get('datetime', [''])[0]
        
        if not all([schedule_id, user_id, title, datetime_str]):
            self.send_json({'success': False, 'message': 'Required fields cannot be empty'})
            return
        
        conn = sqlite3.connect(SCHEDULE_DB)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                UPDATE Schedule 
                SET Title=?, Description=?, DateTime=?
                WHERE ScheduleID=? AND UserID=?
            ''', (title, description, datetime_str, schedule_id, user_id))
            
            conn.commit()
            self.send_json({'success': True, 'message': 'Schedule updated successfully'})
            
        except Exception as e:
            self.send_json({'success': False, 'message': str(e)})
        finally:
            conn.close()

    def handle_delete_schedule(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        data = parse_qs(post_data)
        
        schedule_id = data.get('schedule_id', [''])[0]
        user_id = data.get('user_id', [''])[0]
        
        if not all([schedule_id, user_id]):
            self.send_json({'success': False, 'message': 'Required fields cannot be empty'})
            return
        
        conn = sqlite3.connect(SCHEDULE_DB)
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "DELETE FROM Schedule WHERE ScheduleID=? AND UserID=?",
                (schedule_id, user_id)
            )
            
            conn.commit()
            self.send_json({'success': True, 'message': 'Schedule deleted successfully'})
            
        except Exception as e:
            self.send_json({'success': False, 'message': str(e)})
        finally:
            conn.close()

    def respond_with_html(self, html_content):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(html_content.encode('utf-8'))

    def log_message(self, format, *args):
        # Override to log to our log file instead of stderr
        logger.info(f"{self.address_string()} - {format%args}")

    def log_error(self, format, *args):
        # Override to log errors to our log file
        logger.error(f"{self.address_string()} - {format%args}")

    def handle_error(self, request, client_address):
        # Log unhandled exceptions
        logger.error(f"Error processing request from {client_address}:\n{traceback.format_exc()}")

    # Add this method to the IntranetHandler class
    def send_file(self, filename):
        try:
            with open(filename, 'rb') as f:
                content = f.read().decode('utf-8')
                
                # Handle template variables for login page
                if filename.endswith('login.html'):
                    content = content.replace('{{ request_path }}', self.path)
                
                self.send_response(200)
                if filename.endswith('.html'):
                    self.send_header('Content-type', 'text/html; charset=utf-8')
                elif filename.endswith('.js'):
                    self.send_header('Content-type', 'application/javascript')
                elif filename.endswith('.css'):
                    self.send_header('Content-type', 'text/css')
                self.end_headers()
                self.wfile.write(content.encode('utf-8'))
        except FileNotFoundError:
            self.send_error(404)

    def send_json(self, data):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    # Add this new method to IntranetHandler class
    def handle_schedule_page(self):
        # Check if user is logged in by looking for user_id in query parameters
        params = parse_qs(urlparse(self.path).query)
        user_id = params.get('user_id', [''])[0]
        
        if user_id:
            # User is logged in, show schedule page
            self.send_file('templates/schedule.html')
        else:
            # User is not logged in, redirect to login page
            self.send_response(302)  # Temporary redirect
            self.send_header('Location', '/schedule/login')
            self.end_headers()

    def handle_surgery_page(self):
        # Check if user is authenticated
        params = parse_qs(urlparse(self.path).query)
        is_authenticated = params.get('auth', [''])[0] == 'true'
        
        if is_authenticated:
            # User is authenticated, show surgery schedule page
            self.send_file('templates/surgery_schedule.html')
        else:
            # User is not authenticated, show login page
            self.send_file('templates/surgery_login.html')

    def handle_get_surgeries(self):
        params = parse_qs(urlparse(self.path).query)
        date = params.get('date', [datetime.now().strftime('%Y-%m-%d')])[0]
        department = params.get('department', ['二病区'])[0]  # Default to 二病区 for backward compatibility
        
        conn = sqlite3.connect(SCHEDULE_DB)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT * FROM SurgerySchedule 
                WHERE Date = ? AND Department = ?
                ORDER BY OperationOrder
            ''', (date, department))
            
            columns = [description[0] for description in cursor.description]
            surgeries = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            self.send_json({
                'success': True,
                'surgeries': surgeries
            })
        except Exception as e:
            self.send_json({
                'success': False,
                'message': str(e)
            })
        finally:
            conn.close()

    def handle_add_surgery(self):
        logger.info("Adding new surgery")
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        data = json.loads(post_data)
        
        required_fields = ['Department', 'Date', 'BedNumber', 'PatientName', 'Gender', 'Age', 
                          'HospitalNumber', 'Diagnosis', 'Operation', 'MainSurgeon', 
                          'Assistant', 'AnesthesiaDoctor', 'AnesthesiaType', 
                          'OperationOrder', 'Creator']
        
        if not all(field in data for field in required_fields):
            self.send_json({
                'success': False,
                'message': '所有必填字段都必须填写'
            })
            return
        
        conn = sqlite3.connect(SCHEDULE_DB)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO SurgerySchedule (
                    Department, Date, BedNumber, PatientName, Gender, Age, HospitalNumber,
                    Diagnosis, Operation, MainSurgeon, Assistant, AnesthesiaDoctor,
                    AnesthesiaType, PreOpPrep, OperationOrder, Creator, Editor
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                data['Department'], data['Date'], data['BedNumber'], data['PatientName'], 
                data['Gender'], data['Age'], data['HospitalNumber'], data['Diagnosis'], 
                data['Operation'], data['MainSurgeon'], data['Assistant'], data['AnesthesiaDoctor'],
                data['AnesthesiaType'], data.get('PreOpPrep', ''), data['OperationOrder'],
                data['Creator'], data['Creator']
            ))
            
            conn.commit()
            self.send_json({
                'success': True,
                'message': '手术安排添加成功'
            })
        except Exception as e:
            self.send_json({
                'success': False,
                'message': str(e)
            })
        finally:
            conn.close()

    def handle_edit_surgery(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        data = json.loads(post_data)
        
        if 'ID' not in data:
            self.send_json({
                'success': False,
                'message': '未指定要编辑的手术ID'
            })
            return
        
        # Log the surgery edit attempt with the actual ID from the request
        logger.info(f"Editing surgery ID: {data['ID']}")
        
        required_fields = ['Date', 'BedNumber', 'PatientName', 'Gender', 'Age', 
                            'HospitalNumber', 'Diagnosis', 'Operation', 'MainSurgeon', 
                            'Assistant', 'AnesthesiaDoctor', 'AnesthesiaType', 
                            'OperationOrder']
        
        if not all(field in data for field in required_fields):
            self.send_json({
                'success': False,
                'message': '所有必填字段都必须填写'
            })
            return
        
        conn = sqlite3.connect(SCHEDULE_DB)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                UPDATE SurgerySchedule 
                SET Date=?, BedNumber=?, PatientName=?, Gender=?, Age=?, 
                    HospitalNumber=?, Diagnosis=?, Operation=?, MainSurgeon=?, 
                    Assistant=?, AnesthesiaDoctor=?, AnesthesiaType=?, 
                    PreOpPrep=?, OperationOrder=?, Editor=?, UpdatedAt=CURRENT_TIMESTAMP
                WHERE ID=?
            ''', (
                data['Date'], data['BedNumber'], data['PatientName'], data['Gender'],
                data['Age'], data['HospitalNumber'], data['Diagnosis'], data['Operation'],
                data['MainSurgeon'], data['Assistant'], data['AnesthesiaDoctor'],
                data['AnesthesiaType'], data.get('PreOpPrep', ''), data['OperationOrder'],
                data.get('Editor', '系统用户'), data['ID']
            ))
            
            if cursor.rowcount == 0:
                self.send_json({
                    'success': False,
                    'message': '未找到要编辑的手术记录'
                })
                return
            
            conn.commit()
            self.send_json({
                'success': True,
                'message': '手术安排已更新'
            })
        except Exception as e:
            logger.error(f"Error editing surgery ID {data['ID']}: {str(e)}")
            self.send_json({
                'success': False,
                'message': str(e)
            })
        finally:
            conn.close()

    def handle_delete_surgery(self):
        logger.info("Deleting surgery")
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        data = json.loads(post_data)
        
        if 'id' not in data:
            self.send_json({
                'success': False,
                'message': '未指定要删除的手术ID'
            })
            return
        
        conn = sqlite3.connect(SCHEDULE_DB)
        cursor = conn.cursor()
        
        try:
            cursor.execute('DELETE FROM SurgerySchedule WHERE ID=?', (data['id'],))
            
            if cursor.rowcount == 0:
                self.send_json({
                    'success': False,
                    'message': '未找到要删除的手术记录'
                })
                return
            
            conn.commit()
            self.send_json({
                'success': True,
                'message': '手术安排已删除'
            })
        except Exception as e:
            self.send_json({
                'success': False,
                'message': str(e)
            })
        finally:
            conn.close()

    def handle_export_surgeries(self):
        params = parse_qs(urlparse(self.path).query)
        start_date = params.get('start_date', [''])[0]
        end_date = params.get('end_date', [''])[0]
        department = params.get('department', [''])[0]
        
        conn = sqlite3.connect(SCHEDULE_DB)
        cursor = conn.cursor()
        
        try:
            query = '''
                SELECT Date, Department, BedNumber, PatientName, Gender, Age,
                       HospitalNumber, Diagnosis, Operation, MainSurgeon,
                       Assistant, AnesthesiaDoctor, AnesthesiaType, PreOpPrep,
                       OperationOrder
                FROM SurgerySchedule
                WHERE Department = ?
                AND Date BETWEEN ? AND ?
                ORDER BY Date, OperationOrder
            '''
            cursor.execute(query, (department, start_date, end_date))
            rows = cursor.fetchall()
            
            output = io.StringIO()
            writer = csv.writer(output)
            # Write headers
            writer.writerow(['日期', '病区', '床号', '姓名', '性别', '年龄',
                           '住院号', '临床诊断', '术式', '主刀',
                           '助手', '管床医师', '麻醉', '术前准备', '台次'])
            # Write data
            writer.writerows(rows)
            
            self.send_response(200)
            self.send_header('Content-Type', 'text/csv')
            self.send_header('Content-Disposition', 
                           f'attachment; filename=surgeries_{start_date}_to_{end_date}.csv')
            self.end_headers()
            self.wfile.write(output.getvalue().encode('utf-8-sig'))
            
        finally:
            conn.close()

    def handle_backup_database(self):
        try:
            # Create backup directory if it doesn't exist
            backup_dir = os.path.join(os.path.dirname(SCHEDULE_DB), 'backups')
            os.makedirs(backup_dir, exist_ok=True)
            
            # Create backup filename with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_file = os.path.join(backup_dir, f'schedule_backup_{timestamp}.db')
            
            # Create backup
            shutil.copy2(SCHEDULE_DB, backup_file)
            
            # Create zip file
            zip_file = backup_file + '.zip'
            with zipfile.ZipFile(zip_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(backup_file, os.path.basename(backup_file))
            
            # Remove the unzipped backup
            os.remove(backup_file)
            
            self.send_json({
                'success': True,
                'message': '数据库备份成功',
                'backup_file': os.path.basename(zip_file)
            })
        except Exception as e:
            self.send_json({
                'success': False,
                'message': f'备份失败: {str(e)}'
            })

    def handle_get_history(self):
        params = parse_qs(urlparse(self.path).query)
        start_date = params.get('start_date', [''])[0]
        end_date = params.get('end_date', [''])[0]
        department = params.get('department', [''])[0]
        
        if not all([start_date, end_date, department]):
            self.send_json({
                'success': False,
                'message': '请选择日期范围'
            })
            return
        
        conn = sqlite3.connect(SCHEDULE_DB)
        cursor = conn.cursor()
        
        try:
            # Get all surgeries within date range for the department
            cursor.execute('''
                SELECT * FROM SurgerySchedule 
                WHERE Department = ? 
                AND Date BETWEEN ? AND ?
                ORDER BY Date, OperationOrder
            ''', (department, start_date, end_date))
            
            columns = [description[0] for description in cursor.description]
            surgeries = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            # Group surgeries by date
            history_data = {}
            for surgery in surgeries:
                date = surgery['Date']
                if date not in history_data:
                    history_data[date] = []
                history_data[date].append(surgery)
            
            self.send_json({
                'success': True,
                'history': history_data
            })
        except Exception as e:
            print(f"Error getting history: {str(e)}")
            self.send_json({
                'success': False,
                'message': str(e)
            })
        finally:
            conn.close()

    def handle_surgery_login(self):
        logger.info("Surgery login attempt")
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        data = json.loads(post_data)
        
        username = data.get('username')
        password = data.get('password')
        
        if username == SURGERY_USERNAME and password == SURGERY_PASSWORD:
            self.send_json({
                'success': True,
                'message': '登录成功'
            })
        else:
            self.send_json({
                'success': False,
                'message': '用户名或密码错误'
            })

    def do_POST(self):
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        if path == '/api/surgery/login':
            self.handle_surgery_login()
        elif path == '/api/login':
            self.handle_schedule_login()
        elif path == '/api/register':
            self.handle_schedule_register()
        elif path == '/api/add_schedule':
            self.handle_add_schedule()
        elif path == '/api/edit_schedule':
            self.handle_edit_schedule()
        elif path == '/api/delete_schedule':
            self.handle_delete_schedule()
        elif path == '/api/change_password':
            self.handle_change_password()
        elif path == '/api/delete_account':
            self.handle_delete_account()
        elif path == '/api/surgery/add':
            self.handle_add_surgery()
        elif path == '/api/surgery/edit':
            self.handle_edit_surgery()
        elif path == '/api/surgery/delete':
            self.handle_delete_surgery()
        elif path == '/api/database/backup':
            self.handle_backup_database()
        else:
            self.send_error(404)

# Create a threaded server class
class ThreadedHTTPServer(ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True    # Daemon threads exit when the main program exits
    allow_reuse_address = True   # Allows reuse of address/port

# Add this at the bottom of the file, just before the if __name__ == '__main__': block
def init():
    logger.info("Starting server initialization...")
    try:
        # Create necessary directories
        os.makedirs(PAGES_DIR, exist_ok=True)
        logger.info(f"Created/verified pages directory: {PAGES_DIR}")
        os.makedirs(MESSAGES_DIR, exist_ok=True)
        logger.info(f"Created/verified messages directory: {MESSAGES_DIR}")
        
        # Initialize schedule database
        try:
            init_schedule_db()
            logger.info("Schedule database initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing schedule database: {str(e)}\n{traceback.format_exc()}")
            raise
    except Exception as e:
        logger.error(f"Error during initialization: {str(e)}\n{traceback.format_exc()}")
        raise

# Update the if __name__ == '__main__': block
if __name__ == '__main__':
    try:
        init()
        with ThreadedHTTPServer(("", PORT), IntranetHandler) as httpd:
            logger.info(f"Server started at port {PORT}")
            logger.info("Press Ctrl+C to stop the server")
            httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("\nShutting down server...")
        httpd.server_close()
    except Exception as e:
        logger.error(f"Unhandled exception: {str(e)}\n{traceback.format_exc()}")
        raise