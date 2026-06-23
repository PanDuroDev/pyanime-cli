from setuptools import setup, find_packages
from Cython.Build import cythonize

setup(
    name="anime_cli",
    ext_modules=cythonize("anime_cli.py", compiler_directives={"language_level": "3"}),
    packages=find_packages(include=["src", "src.*"]),
    extras_require={
        "dev": [
            "pytest",
            "pytest-asyncio",
            "respx",
        ],
    },
)
