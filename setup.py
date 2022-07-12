import os

from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(here, 'README.md')) as f:
    README = f.read()
with open(os.path.join(here, 'CHANGES.txt')) as f:
    CHANGES = f.read()

requires = [
    'plaster_pastedeploy',
    'pyramid',
    'pyramid_chameleon',
    'pyramid_jinja2',
    'pyramid_debugtoolbar',
    'pyramid_beaker',
    'pyramid_exclog',
    'requests >= 2.4.2',   # for requests.request(...,json=j)
    'waitress',
    'WebTest',
    'pdfminer.six',
    'Pillow >= 9.2.0',
]

dev_requires = [
    'pyramid_debugtoolbar',
]

tests_requires = [
    'WebTest >= 1.3.1',  # py3 compat
    'pytest',
    'pytest-cov',
]

setup(
    name='eertgif',
    version='0.0',
    description='pdf to newick phylogenetic tree extraction',
    long_description=README + '\n\n' + CHANGES,
    classifiers=[
        'Programming Language :: Python',
        'Framework :: Pyramid',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Internet :: WWW/HTTP :: WSGI :: Application',
    ],
    author='',
    author_email='',
    url='',
    keywords='web pyramid pylons',
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    extras_require={
        'testing': tests_requires,
        'dev': dev_requires,
    },
    install_requires=requires,
    entry_points={
        'paste.app_factory': [
            'main = eertgif:main',
        ],
    },
)
