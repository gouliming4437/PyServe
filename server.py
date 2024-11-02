import http.server
import socketserver
import os
from urllib.parse import urlparse, parse_qs, unquote

PORT = 8000

# Directory where markdown files are stored
PAGES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pages')

# Directory for static files
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')

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
    html = ""
    for line in markdown_text.split('\n'):
        if line.startswith('# '):
            html += f"<h1>{line[2:].strip()}</h1>\n"
        elif line.startswith('## '):
            html += f"<h2>{line[3:].strip()}</h2>\n"
        elif line.startswith('### '):
            html += f"<h3>{line[4:].strip()}</h3>\n"
        elif line.startswith('!['):
            # Handle image syntax: ![alt text](image_url)
            try:
                alt_text = line[2:].split('](')[0]
                image_url = line.split('](')[1].strip(')')
                html += f'<img src="{image_url}" alt="{alt_text}" style="cursor: pointer;" onclick="window.open(this.src)">\n'
            except:
                html += f"<p>{line}</p>\n"
        elif '[file:' in line:
            # Handle file attachment syntax: [file:filename](path/to/file)
            try:
                file_name = line.split('[file:')[1].split('](')[0]
                file_path = line.split('](')[1].strip(')')
                html += f'<p class="attachment"><a href="{file_path}" target="_blank"><img src="/static/images/file-icon.png" class="file-icon" alt="File">{file_name}</a></p>\n'
            except:
                html += f"<p>{line}</p>\n"
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
                html += f"<p>{html_line}</p>\n"
            except:
                html += f"<p>{line}</p>\n"
        else:
            html += f"<p>{line}</p>\n"
    return html

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
    # Handle for loops first
    if 'pages' in kwargs and isinstance(kwargs['pages'], list):
        # Find the for loop section
        start = template_content.find('{% for page in pages %}')
        end = template_content.find('{% endfor %}')
        if start != -1 and end != -1:
            # Get the template inside the loop
            loop_template = template_content[start + len('{% for page in pages %}'):end]
            # Generate HTML for each page
            pages_html = ''
            for page in kwargs['pages']:
                page_content = loop_template
                for key, value in page.items():
                    placeholder = '{{ page.' + key + ' }}'
                    page_content = page_content.replace(placeholder, str(value))
                pages_html += page_content
            # Replace the entire for loop section with the generated HTML
            template_content = (
                template_content[:start] + 
                pages_html + 
                template_content[end + len('{% endfor %}'):]
            )

    # Handle simple placeholders
    for key, value in kwargs.items():
        placeholder = '{{ ' + key + ' }}'
        template_content = template_content.replace(placeholder, str(value))
    
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

class IntranetHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urlparse(self.path)
        path = unquote(parsed_path.path)
        query = parse_qs(parsed_path.query)

        if path == '/':
            self.handle_index()
        elif path.startswith('/page/'):
            page_name = path.split('/page/')[-1]
            self.handle_page(page_name)
        elif path.startswith('/search'):
            search_query = query.get('q', [''])[0]
            self.handle_search(search_query)
        else:
            # Let SimpleHTTPRequestHandler handle static files
            super().do_GET()

    def handle_index(self):
        parsed_path = urlparse(self.path)
        query = parse_qs(parsed_path.query)
        selected_category = query.get('category', [None])[0]
        selected_subcategory = query.get('subcategory', [None])[0]
        
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
                    f'<li><a href="/?category={main_cat}&subcategory={sub_cat}" '
                    f'class="{sub_active_class}">{sub_cat}</a></li>'
                )
            
            # Add the category with its dropdown
            menu_html.append(f'''
                <li class="dropdown">
                    <a href="/?category={main_cat}" class="dropbtn{active_class}">{main_cat}</a>
                    <ul class="dropdown-content">
                        {' '.join(sub_menu)}
                    </ul>
                </li>
            ''')

        # Second pass: collect pages
        pages_data = []
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
                                
                                # Check if page matches selected category/subcategory
                                should_include = True
                                if selected_category:
                                    if 'classifications' in metadata:
                                        matches = False
                                        for main_cat, sub_cats in metadata['classifications'].items():
                                            if main_cat == selected_category:
                                                if selected_subcategory:
                                                    matches = selected_subcategory in sub_cats
                                                else:
                                                    matches = True
                                                break
                                        should_include = matches
                                    else:
                                        should_include = False
                                
                                if should_include:
                                    # Format classifications for display
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
                                    
                                    base_filename = os.path.splitext(filename)[0]
                                    pages_data.append({
                                        'title': title,
                                        'classification': classification_text,
                                        'filename': base_filename
                                    })
                                break
                        except UnicodeDecodeError:
                            continue
                    if content is None:
                        print(f"Failed to decode file {filename} with any encoding")
                        continue
                except Exception as e:
                    print(f"Error reading file {filename}: {str(e)}")
                    continue

        # Read and render the template
        template = read_template('index.html')
        html_content = render_template(template,
            title=f"Intranet Site{' - ' + selected_category if selected_category else ''}",
            menu_html=''.join(menu_html),
            pages=pages_data if pages_data else [],
            category_title=selected_category if selected_category else 'All'
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
            
            # Read and render the template
            template = read_template('page.html')
            html_content = render_template(template,
                title=title,
                menu_html=''.join(menu_html),
                classification=classification_text,
                content=html_content
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
                    # Try different encodings
                    content = None
                    for encoding in ['utf-8-sig', 'utf-8', 'gb18030']:
                        try:
                            with open(filepath, 'r', encoding=encoding) as f:
                                content = f.read()
                                if query.lower() in content.lower():
                                    metadata, _ = parse_front_matter(content)
                                    title = metadata.get('title', filename.replace('.md', ''))
                                    classifications = metadata.get('classification', ['General'])
                                    classification_text = ', '.join(classifications)
                                    results.append({
                                        'title': title,
                                        'filename': filename.replace('.md', ''),
                                        'classification': classification_text
                                    })
                                break  # If successful, break the encoding loop
                        except UnicodeDecodeError:
                            continue
                    if content is None:
                        print(f"Failed to decode file {filename} with any encoding")
                        continue
                except Exception as e:
                    print(f"Error reading file {filename}: {str(e)}")
                    continue

        # Build search results HTML
        results_html = ""
        if results:
            for page in results:
                results_html += f"<li><strong>{page['title']}</strong> - {page['classification']} [<a href='/page/{page['filename']}'>View Page</a>]</li>"
        else:
            results_html = "<li>No results found.</li>"

        html_content = render_template(read_template('search.html'), query=query, results=results_html)
        self.respond_with_html(html_content)

    def respond_with_html(self, html_content):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(html_content.encode('utf-8'))

    def log_message(self, format, *args):
        # Override to prevent printing to stderr on each request
        return

with socketserver.TCPServer(("", PORT), IntranetHandler) as httpd:
    print(f"Serving at port {PORT}")
    httpd.serve_forever()