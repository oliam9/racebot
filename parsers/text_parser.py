"""
Plain text file parser.
"""

from .document_parser import DocumentParser


class TextParser(DocumentParser):
    """Parser for plain text files."""
    
    def extract_text(self, file_bytes: bytes, filename: str) -> str:
        """
        Extract text from plain text file.
        
        Args:
            file_bytes: Text file bytes
            filename: Original filename
            
        Returns:
            Extracted text content
            
        Raises:
            ValueError: If text cannot be decoded
        """
        try:
            import chardet
        except ImportError:
            # Fallback to UTF-8 if chardet not available
            chardet = None
        
        # Detect encoding
        if chardet:
            detection = chardet.detect(file_bytes)
            encoding = detection.get('encoding', 'utf-8')
        else:
            encoding = 'utf-8'
        
        try:
            text = file_bytes.decode(encoding)
            if not text.strip():
                raise ValueError("Text file is empty")
            return text
        except UnicodeDecodeError:
            # Try common encodings as fallback
            for fallback_encoding in ['utf-8', 'latin-1', 'cp1252']:
                try:
                    text = file_bytes.decode(fallback_encoding)
                    if text.strip():
                        return text
                except UnicodeDecodeError:
                    continue
            
            raise ValueError("Could not decode text file (unknown encoding)")
