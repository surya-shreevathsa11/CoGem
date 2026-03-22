from setuptools import setup, find_packages

setup(
    name="devai",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        "rich>=10.0.0",
    ],
    entry_points={
        "console_scripts": [
            "devai=devai.cli:main",
        ],
    },
)
