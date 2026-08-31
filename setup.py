from setuptools import setup, find_packages

setup(
  name="KOLPAK",
  version="1.1.0",
  description="VK id parser",
  author="peath88",
  packages=find_packages(),
  install_requires=[
    "vk_api>=11.9.0",
  ],
  entry_points={
    "console_scripts": [
      "KOLPAK=KOLPAK:main",
      "kolpak=KOLPAK:main",
    ],
  },
  python_requires=">=3.6",
)
