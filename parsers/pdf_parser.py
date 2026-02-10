"""
PDF document parser using pdfplumber.
"""

from .document_parser import DocumentParser
import io


class PDFParser(DocumentParser):
    """Parser for PDF documents."""
    
    def extract_text(self, file_bytes: bytes, filename: str) -> str:
        """
        Extract text from PDF document.
        
        Args:
            file_bytes: PDF file bytes
            filename: Original filename
            
        Returns:
            Extracted text content
            
        Raises:
            ValueError: If PDF is invalid or corrupted
        """
        try:
            import pdfplumber
        except ImportError:
            raise ImportError(
                "pdfplumber not installed. Run: pip install pdfplumber"
            )
        
        try:
            text_content = []
            
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                if not pdf.pages:
                    raise ValueError("PDF document is empty")
                
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_content.append(page_text)
                    
                    # Also extract tables as structured text
                    tables = page.extract_tables()
                    for table in tables:
                        # Convert table to text representation
                        for row in table:
                            if row:
                                text_content.append(' | '.join(str(cell or '') for cell in row))
            
            if not text_content:
                raise ValueError("Could not extract any text from PDF")
            
            return '\n\n'.join(text_content)
            
        except Exception as e:
            if isinstance(e, ValueError):
                raise
            raise ValueError(f"Failed to parse PDF: {str(e)}")
