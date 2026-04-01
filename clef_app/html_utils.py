"""Utility functions for HTML generation and markdown conversion."""

import markdown2


def markdown_to_html(markdown_text: str) -> str:
    """Convert markdown text to HTML.
    
    Args:
        markdown_text: Text in markdown format
        
    Returns:
        HTML string
    """
    return markdown2.markdown(markdown_text, extras=['tables', 'fenced-code-blocks'])


def create_article_html(title: str, subtitle: str, content: str, image_path: str = None) -> str:
    """Create plain HTML article without any styling.
    
    Args:
        title: Article title
        subtitle: Article subtitle
        content: Article content (will be converted from markdown to HTML if needed)
        image_path: Optional path to header image
        
    Returns:
        Plain HTML document as string
    """
    # Convert markdown content to HTML
    html_content = markdown_to_html(content)
    
    # Build the image HTML if provided
    image_html = ""
    if image_path:
        image_html = f"<img src=\"{image_path}\" alt=\"Article header image\">\n"
    
    # Create plain HTML document with no styling
    html = f"""<!DOCTYPE html>
<html>
<head>
<title>{title}</title>
</head>
<body>
<h1>{title}</h1>
<h2>{subtitle}</h2>
{image_html}
{html_content}
</body>
</html>"""
    
    return html


