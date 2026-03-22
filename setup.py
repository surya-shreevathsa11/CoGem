from setuptools import setup, find_packages

setup(
    name="cogem",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        "rich>=10.0.0",
        "prompt_toolkit>=3.0.0",
    ],
    entry_points={
        "console_scripts": [
            "cogem=cogem.cli:main",
        ],
    },
)
