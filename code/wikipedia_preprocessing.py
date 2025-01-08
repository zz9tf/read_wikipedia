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

def _clean_text(raw_text):
    cleaned_text = html.unescape(raw_text)
    cleaned_text = re.sub(r".*}}", "", raw_text, count=1, flags=re.DOTALL)
    cleaned_text = re.sub(r'\{\{.*?\}\}', '', cleaned_text, flags=re.DOTALL)
    cleaned_text = re.sub(r"'''(.*?)'''", r'\1', cleaned_text)
    cleaned_text = re.sub(r'\[\[(?:[^\]|]+\|)?([^\]]+)\]\]', r'\1', cleaned_text)
    return cleaned_text

def _get_abstract(text, title, raw_text):
    # Split the text into lines
    abstract = []
    print_str = ""
    for line in text.split('\n'):
        line = line.strip()
        if line.startswith("{{") and line.endswith("}}"):
            continue
        abstract.append(line)
    abstract = _clean_text("".join(abstract))
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
    no_abstract = False
    for i, section in enumerate(raw_sections):
        if i == 0:
            # Process abstract
            abstract, abstract_print_str = _get_abstract(section, page['title'], page['raw_page'])
            print_str += abstract_print_str
            old_section_title = 'abstract'
            if len(abstract) > 0:
                paper_content += f'{abstract}\n\n'
                file_dict['sections']['abstract'] = [start, len(paper_content)-2]
            else:
                no_abstract = True
        else:
            # Process body
            lines = section.split('\n')
            section_title = lines[0].strip('= ')
            section_content = _clean_text("\n".join(lines[1:]))
            if not section.startswith('='):
                assert old_section_title == 'abstract' or len(file_dict['sections'][old_section_title]) > 0,\
                    f"No section at title {page['title']} with section {old_section_title}\n{file_dict['sections'][old_section_title]}"
                old_section_title = section_title
                start = len(paper_content)
                paper_content += f'{section_content}\n\n'
                file_dict['sections'][section_title] = [start, len(paper_content)-2]
            else:
                assert old_section_title is not None, 'old_section_title shouldn\'t be None'
                paper_content += f'{section_content}\n\n'
                file_dict['sections'][old_section_title] = [start, len(paper_content)-2]
    if len(file_dict['sections']) == 0:
        print_str += f"[documetn reader] Detect invalided document with no sections {page['title']}\n{page['raw_page']}\n"
        return None, None, None, print_str
    else:
        return paper_content, file_dict, no_abstract, print_str
    


import os
import json
from multiprocessing.pool import ThreadPool

# Shared data structures
titles = []
length = []
section_titles = {}
lock = None  # Lock to prevent race conditions during updates to shared data structures

def process_file(file_path):
    print(f"** Start file: {os.path.basename(file_path)}")
    global lock
    local_titles = []
    local_length = []
    local_section_titles = {}

    file_size = os.path.getsize(file_path)
    cur_size = 0
    show_present = 0
    with open(file_path, 'r') as input_file:
        for line in input_file:
            cur_size += len(line)
            data = json.loads(line)
            page = _go_over_string_element(data['page'])
            if page:
                paper_content, file_dict, _, _ = _read_page(page)
                if paper_content:
                    local_titles.append(file_dict['title'])
                    local_length.append(len(paper_content))
                    for key in file_dict['sections']:
                        local_section_titles[key] = local_section_titles.get(key, 0) + 1
            if cur_size >= file_size * show_present:
                print(f"Processing file: {os.path.basename(file_path)} with {show_present*100}%")
                show_present += 0.1

    # Update shared data structures
    with lock:
        titles.extend(local_titles)
        length.extend(local_length)
        for key, count in local_section_titles.items():
            section_titles[key] = section_titles.get(key, 0) + count
        print(f">> Finished file: {os.path.basename(file_path)}")
    return local_titles, local_length, local_section_titles

# Main code
if __name__ == "__main__":
    from multiprocessing import Manager

    # Use a manager to create a lock for shared access
    manager = Manager()
    lock = manager.Lock()

    data_dir = '/home/zhengzheng/scratch0/projects/Fine-Tuned-GPT-2-with-articles-ground-truth-main/code/llamaIndex/.cache'
    filenames = sorted(list(os.listdir(data_dir)), key=lambda x: int(x.split('_')[-1].split('.')[0]))
    file_paths = [os.path.join(data_dir, filename) for filename in filenames]

    print('Start processing ...')
    process_file(file_paths[0])
    # # Use ThreadPool for multithreading
    # with ThreadPool(20) as pool:  # Adjust the number of threads as per your system capabilities
    #     pool.map(process_file, file_paths)

    # Save results
    output = {
        "titles": titles,
        "length": length,
        "section_titles": section_titles
    }

    output_file = "processed_data.json"
    with open(output_file, 'w') as json_file:
        json.dump(output, json_file, indent=4)

    print(f"Results saved to {output_file}")