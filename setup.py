import sys
from distutils.core import setup
from distutils.command.build_py import build_py

if sys.version_info <= (3, 2):
    sys.stderr.write("Perevod requires Python 3.2+\n")
    sys.exit(1)

with open('README.rst', 'br') as f:
    desc = f.read().decode()

setup(
    name='perevod',
    description='Lightweight selection translator (GTK+)',
    long_description=desc,
    license='BSD',
    version='beta',
    author='naspeh',
    author_email='naspeh@ya.ru',
    url='http://github.com/naspeh/perevod/',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: X11 Applications :: GTK',
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: BSD License',
        'Operating System :: Linux',
        'Programming Language :: Python :: 3',
        'Topic :: Office/Business'
    ],
    platforms='any',
    py_modules=['perevod'],
    scripts=['perevod'],
    cmdclass={'build_py': build_py}
)
