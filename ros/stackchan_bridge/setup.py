from setuptools import find_packages, setup

package_name = "stackchan_bridge"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="StackChan Bridge Maintainers",
    maintainer_email="maintainers@example.com",
    description="PC-side ROS 2 bridge facade for StackChan command routing.",
    license="MIT",
    entry_points={
        "console_scripts": [
            "stackchan_bridge_node = stackchan_bridge.ros_node:main",
            "stackchan_speech_node = stackchan_bridge.speech_node:main",
        ],
    },
)
