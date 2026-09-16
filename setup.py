from setuptools import setup, find_packages

setup(
    name="agent-commander",
    version="0.1.0",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "agent-commander=agent_commander.cli:main",
            "agent_commander=agent_commander.cli:main",
            "ac=agent_commander.cli:main",
        ],
    },
)
