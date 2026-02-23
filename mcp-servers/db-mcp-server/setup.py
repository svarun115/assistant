"""
Setup script for Journal MCP Server
Install with: pip install -e .
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README for long description
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text(encoding="utf-8") if readme_file.exists() else ""

# Read requirements
requirements_file = Path(__file__).parent / "requirements.txt"
requirements = []
if requirements_file.exists():
    with open(requirements_file, 'r', encoding='utf-8') as f:
        requirements = [
            line.strip() 
            for line in f 
            if line.strip() and not line.startswith('#')
        ]

setup(
    name="journal-mcp-server",
    version="1.0.0",
    description="MCP Server for Personal Journal Database with PostgreSQL",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Varun Shirivastava",
    url="https://github.com/svarun115/JournalMCPServer",
    packages=find_packages(exclude=["tests", "tests.*", "docs"]),
    py_modules=[
        "server",
        "config",
        "database",
        "models",
        "repositories",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "journal-mcp-server=server:cli_entry",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Application Frameworks",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    keywords="mcp server journal postgresql database",
    project_urls={
        "Bug Reports": "https://github.com/svarun115/JournalMCPServer/issues",
        "Source": "https://github.com/svarun115/JournalMCPServer",
    },
)
