import os
import zipfile
import xml.etree.ElementTree as ET

def process_scorm_package(zip_file, scorm_id_str, upload_base_folder):
    """
    Extracts a SCORM zip file into upload_base_folder/scorm/<scorm_id_str>/
    and parses imsmanifest.xml to locate the launch file (href).
    Returns (launch_href, error_message).
    """
    scorm_folder = os.path.join(upload_base_folder, 'scorm', str(scorm_id_str))
    os.makedirs(scorm_folder, exist_ok=True)

    zip_path = os.path.join(scorm_folder, 'package.zip')
    zip_file.save(zip_path)

    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(scorm_folder)
    except Exception as e:
        return None, f"Failed to extract SCORM zip package: {e}"

    manifest_path = os.path.join(scorm_folder, 'imsmanifest.xml')
    if not os.path.exists(manifest_path):
        return None, "Invalid SCORM package: imsmanifest.xml file missing."

    try:
        tree = ET.parse(manifest_path)
        root = tree.getroot()

        # Clean XML namespaces for tag matching
        for elem in root.iter():
            if '}' in elem.tag:
                elem.tag = elem.tag.split('}', 1)[1]

        # Locate first resource with an href attribute
        resource = root.find('.//resource')
        if resource is not None and 'href' in resource.attrib:
            launch_href = resource.attrib['href']
            return launch_href, None

        # Fallback to common SCORM launch filenames
        for root_dir, dirs, files in os.walk(scorm_folder):
            for f in files:
                if f.lower() in ['index.html', 'story.html', 'index_lms.html', 'launch.html']:
                    rel_path = os.path.relpath(os.path.join(root_dir, f), scorm_folder)
                    return rel_path.replace('\\', '/'), None

        return None, "Could not identify launch HTML file in SCORM manifest."
    except Exception as e:
        return None, f"Error parsing SCORM imsmanifest.xml: {e}"
