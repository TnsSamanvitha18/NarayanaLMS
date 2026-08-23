import re

def parse_gdrive_url(url):
    """
    Parses a Google Drive or Google Docs URL and returns a tuple:
    (is_gdrive, embed_url, detected_type, file_id)

    Supported Google Drive / Docs URL formats:
    1. https://drive.google.com/file/d/{FILE_ID}/view?usp=sharing -> /file/d/{FILE_ID}/preview
    2. https://drive.google.com/open?id={FILE_ID} -> /file/d/{FILE_ID}/preview
    3. https://drive.google.com/uc?id={FILE_ID} -> /file/d/{FILE_ID}/preview
    4. https://docs.google.com/presentation/d/{ID}/edit -> /presentation/d/{ID}/embed
    5. https://docs.google.com/document/d/{ID}/edit -> /document/d/{ID}/preview
    6. https://docs.google.com/spreadsheets/d/{ID}/edit -> /spreadsheets/d/{ID}/preview
    7. https://drive.google.com/drive/folders/{ID} -> /embeddedfolderview?id={ID}#list
    """
    if not url or not isinstance(url, str):
        return False, url or '', 'External Link', None

    clean_url = url.strip()

    # Check if Google Drive / Docs domain
    if 'drive.google.com' not in clean_url and 'docs.google.com' not in clean_url:
        return False, clean_url, 'External Link', None

    file_id = None
    file_type = 'Google Drive Resource'
    embed_url = clean_url

    # Format 1: drive.google.com/file/d/{FILE_ID}/...
    m_file = re.search(r'drive\.google\.com/file/d/([a-zA-Z0-9_-]+)', clean_url)
    if m_file:
        file_id = m_file.group(1)
        embed_url = f"https://drive.google.com/file/d/{file_id}/preview"
        file_type = 'Google Drive File'

    # Format 2: drive.google.com/open?id={FILE_ID} or /uc?id={FILE_ID}
    elif 'id=' in clean_url and 'drive.google.com' in clean_url:
        m_id = re.search(r'[?&]id=([a-zA-Z0-9_-]+)', clean_url)
        if m_id:
            file_id = m_id.group(1)
            embed_url = f"https://drive.google.com/file/d/{file_id}/preview"
            file_type = 'Google Drive File'

    # Format 3: docs.google.com/presentation/d/{ID}
    elif 'docs.google.com/presentation/d/' in clean_url:
        m_pres = re.search(r'docs\.google\.com/presentation/d/([a-zA-Z0-9_-]+)', clean_url)
        if m_pres:
            file_id = m_pres.group(1)
            embed_url = f"https://docs.google.com/presentation/d/{file_id}/embed"
            file_type = 'Google Slides (PPT)'

    # Format 4: docs.google.com/document/d/{ID}
    elif 'docs.google.com/document/d/' in clean_url:
        m_doc = re.search(r'docs\.google\.com/document/d/([a-zA-Z0-9_-]+)', clean_url)
        if m_doc:
            file_id = m_doc.group(1)
            embed_url = f"https://docs.google.com/document/d/{file_id}/preview"
            file_type = 'Google Document'

    # Format 5: docs.google.com/spreadsheets/d/{ID}
    elif 'docs.google.com/spreadsheets/d/' in clean_url:
        m_sheet = re.search(r'docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)', clean_url)
        if m_sheet:
            file_id = m_sheet.group(1)
            embed_url = f"https://docs.google.com/spreadsheets/d/{file_id}/preview"
            file_type = 'Google Spreadsheet'

    # Format 6: drive.google.com/drive/folders/{ID}
    elif 'folders/' in clean_url:
        m_folder = re.search(r'folders/([a-zA-Z0-9_-]+)', clean_url)
        if m_folder:
            file_id = m_folder.group(1)
            embed_url = f"https://drive.google.com/embeddedfolderview?id={file_id}#list"
            file_type = 'Google Drive Folder'

    return True, embed_url, file_type, file_id
