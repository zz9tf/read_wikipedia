
import html
import re
from lxml import etree
from xml.etree.ElementTree import XMLPullParser

def _go_over_string_element(xml_data):
    # Parse the string as a file-like object
    root = etree.fromstring(xml_data)
    redirect = root.find('redirect')
    title = root.findtext('title')
    text_element = root.find(".//text")  # Find the text element (can be nested)
    if redirect is not None or text_element is None or text_element.text is None: return None
    text = text_element.text.strip()
    
    return {'title': title, 'text': text, 'raw_page': xml_data}

def remove_self_closing_ref(text):
    """
    Removes <ref /> self-closing tags.
    """
    result = []
    i = 0
    
    while i < len(text):
        # Check for the beginning of a self-closing <ref /> tag
        if text[i:i+4] == '<ref' and '/>' in text[i+4:]:
            end_idx = text.find('>', i)
            if text[end_idx - 1] == '/':  # Confirm it's self-closing
                i = end_idx + 1  # Skip the entire self-closing tag
            else:
                result.append(text[i])
                i += 1
        else:
            result.append(text[i])
            i += 1
    
    return ''.join(result)

def remove_ref_with_content(text):
    """
    Removes <ref*?.>...</ref> tags using a stack.
    """
    stack = []
    result = []
    i = 0
    
    while i < len(text):
        # Check for opening <ref> tag
        if text[i:i+4] == '<ref' and '>' in text[i+4:]:
            stack.append(i)  # Push position of opening tag onto stack
            i += 4  # Skip the opening tag
        # Check for closing </ref> tag
        elif text[i:i+6] == '</ref>' and len(stack) > 0:
            stack.pop()  # Pop the last opening tag position
            i += 6  # Skip the closing tag
        elif len(stack) == 0:
            result.append(text[i])  # Add to result if not inside a <ref ...>...</ref> block
            i += 1
        else:
            i += 1  # Skip characters within the <ref>...</ref> block
    
    return ''.join(result)

def remove_braces_content(text):
    stack = []
    result = []
    i = 0

    while i < len(text):
        char = text[i]
        if char == '{' and i + 1 < len(text) and text[i + 1] == '{':
            # Push the current length of result onto the stack to remember where the brace started
            stack.append(len(result))
            i += 1  # Skip the second '{'
        elif char == '}' and i + 1 < len(text) and text[i + 1] == '}' and len(stack) > 0:
            start = stack.pop()
            block_content = ''.join(result[start:])
            if '|' in block_content:
                if len(block_content.split('|')) == 2:
                    # Keep only the content is only two part splitted by '|'
                    keep_content = block_content.split('|')[1]
                    result = result[:start] + list(keep_content)
                else:
                    result = result[:start]
            i += 1  # Skip the second '}'
        else:
            # Append character to the result only if not within braces
            result.append(char)
        i += 1
    
    # Join the result back into a string
    return ''.join(result)

def remove_square_brackets(text):
    square_stack = []
    result = []
    i = 0

    while i < len(text):
        char = text[i]

        if char == '[' and i + 1 < len(text) and text[i + 1] == '[':
            # Start of a square bracket block
            square_stack.append(len(result))  # Save the position in result
            i += 1  # Skip the second '['
        elif char == ']' and i + 1 < len(text) and text[i + 1] == ']' and len(square_stack) > 0:
            # End of a square bracket block
            start = square_stack.pop()
            block_content = ''.join(result[start:])
            if '|' in block_content:
                # Keep only the content after '|' for other cases
                keep_content = block_content.split('|')[-1]
                result = result[:start] + list(keep_content)
            i += 1  # Skip the second ']'
        else:
            # Add the character to the result if not within brackets or after processing
            result.append(char)
        i += 1

    return ''.join(result)

def _clean_text(raw_text):
    cleaned_text = html.unescape(raw_text)
    # Remove <ref /> tag without greedy
    cleaned_text = remove_self_closing_ref(cleaned_text)
    # Remove <ref> tag without greedy
    cleaned_text = remove_ref_with_content(cleaned_text)
    # Remove { }
    cleaned_text = remove_braces_content(cleaned_text)
    # Remove <!-- ... -->
    cleaned_text = re.sub(r'<!--.*?-->', '', cleaned_text, flags=re.DOTALL)
    # Remove ''' '''
    cleaned_text = re.sub(r"'''(.*?)'''", r'\1', cleaned_text)
    # Remove [[ | target]] -> target
    cleaned_text = remove_square_brackets(cleaned_text)
    cleaned_text = cleaned_text.strip() + '\n'
    
    return cleaned_text

def _get_abstract(text, title, raw_text):
    # Split the text into lines
    abstract = []
    print_str = ""
    abstract = _clean_text(text)
    if len(abstract) <= 0:
    #     print(raw_text[:10000])
    #     print(">>>>>>>>>>>>>>>")
    #     print(abstract.strip())
        print_str += f"Not find abstract at title {title}\n"
        
    # assert len(abstract) > 0, f"Not find abstract at title {title}"  
    
    return abstract, print_str

def _read_page(page):
    file_dict = {}
    print_str = ""
    file_dict['title'] = page['title']
    page_text = page['text']
    file_dict['sections'] = {}
    
    paper_content = "Title: {}\n\n".format(file_dict['title'])
    start = len(paper_content)
    
    raw_sections = re.split(r'(?m)^==\s*', page_text)
    old_section_title = None
    
    current_section = ""
    abstract, abstract_print_str = _get_abstract(raw_sections[0], page['title'], page['raw_page'])
    print_str += abstract_print_str
    old_section_title = 'abstract'
    if len(abstract) > 0:
        current_section = f'{abstract}\n'
    should_skip = False
    
    for section in raw_sections[1:]:
        # Process body
        lines = section.split('\n')
        section_title = lines[0].strip('= ')
        section_content = _clean_text("\n".join(lines[1:]))
        if not section.startswith('='):
            if len(current_section.strip()) > 0:
                paper_content += current_section
                file_dict['sections'][old_section_title] = [start, len(paper_content)-1]
                current_section = ""
            if section_title.lower() in ['references', 'external links', 'see also', 'further reading', 'literature and sources']:
                should_skip = True
            else:
                should_skip = False
            if should_skip: continue
            old_section_title = section_title
            start = len(paper_content)
            current_section = f'{section_content}\n'
        elif not should_skip:
            assert old_section_title is not None, 'old_section_title shouldn\'t be None'
            current_section += f'{section_content}\n'
    
    
    if len(file_dict['sections']) == 0:
        print_str += f"[documetn reader] Detect invalided document with no sections {page['title']}\n{page['raw_page']}\n"
        return None, None, print_str
    else:
        return paper_content, file_dict, print_str