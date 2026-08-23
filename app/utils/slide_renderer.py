import os
import pypdfium2 as pdfium
from PIL import Image

def render_pdf_to_slide_images(pdf_path, output_dir, rel_prefix):
    """
    Renders every page of a PDF file into high-res PNG slide images using pypdfium2 (Chrome PDFium).
    Returns a list of image relative URLs: ['/courses/courseware/1/slide_img/slide_1.png', ...]
    """
    image_urls = []
    if not os.path.exists(pdf_path):
        return image_urls

    os.makedirs(output_dir, exist_ok=True)

    try:
        pdf = pdfium.PdfDocument(pdf_path)
        num_pages = len(pdf)

        for i in range(num_pages):
            img_filename = f"slide_{i+1}.png"
            img_save_path = os.path.join(output_dir, img_filename)

            # Render at 2x scale (approx 150-200 DPI) for crisp slide display
            if not os.path.exists(img_save_path):
                page = pdf[i]
                image = page.render(scale=2).to_pil()
                image.save(img_save_path, "PNG")

            image_urls.append(f"{rel_prefix}/{img_filename}")
        
        pdf.close()
    except Exception as e:
        print(f"Error rendering PDF to slide images: {e}")

    return image_urls
