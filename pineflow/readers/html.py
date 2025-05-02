import os
from pathlib import Path
from typing import List

from pineflow.core.document import Document
from pineflow.core.readers import BaseReader


class HTMLReader(BaseReader):
    """Load HTML file and extract text from a specific tag.

    Args:
        tag (str): HTML tag to extract. Defaults to ``section``.
    """
    
    tag: str = "section"

    def load_data(self, input_file: str) -> List[Document]:
        """Loads data from the specified directory.
        
        Args:
            input_file (str): File path to load.
        """
        try:
            from bs4 import BeautifulSoup  # noqa: F401
        except ImportError:
            raise ImportError("beautifulsoup4 package not found, please install it with `pip install beautifulsoup4`")
        
        if not os.path.isfile(input_file):
            raise ValueError(f"File `{input_file}` does not exist")
        
        input_file = str(Path(input_file).resolve())

        with open(input_file, encoding="utf-8") as html_file:
            soup = BeautifulSoup(html_file, "html.parser")

        tags = soup.find_all(self.tag)
        documents = []

        for tag in tags:
            tag_text = self._extract_text_from_tag(tag)

            metadata = {
                "tag": self.tag,
                "source": input_file,
            }

            doc = Document(
                text=tag_text,
                metadata=metadata,
            )

            documents.append(doc)

        return documents

    def _extract_text_from_tag(self, tag) -> str:
        """Extract the text from an HTML tag, ignoring other nested tags."""
        try:
            from bs4 import NavigableString  # noqa: F401
        except ImportError:
            raise ImportError("beautifulsoup4 package not found, please install it with `pip install beautifulsoup4`")

        texts = []

        for elem in tag.children:
            # Check if the element is a text node, not a tag
            if isinstance(elem, NavigableString):
                if elem.strip():
                    texts.append(elem.strip())
            # Ignore any tag that matches the main tag being processed (to avoid recursion)
            elif elem.name == self.tag:
                continue
            else:
                texts.append(elem.get_text().strip())

        return "\n".join(texts)
