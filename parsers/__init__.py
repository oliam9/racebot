"""
Base document parser interface.
"""

from abc import ABC, abstractmethod
from typing import Optional


class DocumentParser(ABC):
    """Abstract base class for document parsers."""
    
    @abstractmethod
    def extract_text(self, file_bytes: bytes, filename: str) -> str:
        """
        Extract text content from document.
        
        Args:
            file_bytes: Raw file bytes
            filename: Original filename (for extension detection)
            
        Returns:
            Extracted text content
            
        Raises:
            ValueError: If file format is invalid or unsupported
        """
        pass
    
    @staticmethod
    def get_parser(filename: str) -> 'DocumentParser':
        """
        Factory method to get appropriate parser based on file extension.
        
        Args:
            filename: Filename with extension
            
        Returns:
            Appropriate DocumentParser instance
            
        Raises:
            ValueError: If file extension is not supported
        """
        from .pdf_parser import PDFParser
        from .docx_parser import DocxParser
        from .text_parser import TextParser
        
        ext = filename.lower().split('.')[-1] if '.' in filename else ''
        
        if ext == 'pdf':
            return PDFParser()
        elif ext in ['docx', 'doc']:
            return DocxParser()
        elif ext in ['txt', 'text']:
            return TextParser()
        
        raise ValueError(
            f"Unsupported file format: .{ext}. "
            f"Supported: PDF, DOCX, TXT"
        )
