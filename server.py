import http.server
import socketserver
from socketserver import ThreadingMixIn
import os
from urllib.parse import urlparse, parse_qs, unquote
import os.path, time
from operator import itemgetter
from pathlib import Path

PORT = 8000

# Base content directory
CONTENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'content')

# Directory where markdown files are stored
PAGES_DIR = os.path.join(CONTENT_DIR, 'pages')

# Directory where message files are stored
MESSAGES_DIR = os.path.join(CONTENT_DIR, 'messages')

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

class IntranetHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urlparse(self.path)
        path = unquote(parsed_path.path)
        query = parse_qs(parsed_path.query)

        if path == '/':
            self.handle_index()
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

    def respond_with_html(self, html_content):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(html_content.encode('utf-8'))

    def log_message(self, format, *args):
        # Override to prevent printing to stderr on each request
        return

# Create a threaded server class
class ThreadedHTTPServer(ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True    # Daemon threads exit when the main program exits
    allow_reuse_address = True   # Allows reuse of address/port

# Replace the original server start code at the bottom of the file with:
if __name__ == '__main__':
    # Create necessary directories if they don't exist
    os.makedirs(PAGES_DIR, exist_ok=True)
    os.makedirs(MESSAGES_DIR, exist_ok=True)
    
    try:
        with ThreadedHTTPServer(("", PORT), IntranetHandler) as httpd:
            print(f"Server started at port {PORT}")
            print("Press Ctrl+C to stop the server")
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        httpd.server_close()