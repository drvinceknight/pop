import pathlib
import distutils.dir_util
import subprocess
import sys
import tempfile

import jinja2
import markdown
import nbconvert
import nbformat
import proselint
from invoke import task

import known

WEB_ROOT = "pop"
TITLE = "Principles of Presentation"
DESCRIPTION = "A page with principles for effective presentations"
KEYWORDS = "presentations, best presentations, good presentations, beamer"
AUTHOR = "Vince Knight"

REPO_ROOT = pathlib.Path(__file__).parent
SOURCE_FILE_PATH = REPO_ROOT / "main.md"


def get_markdown_files_to_check(root=REPO_ROOT, source_file_path=SOURCE_FILE_PATH):
    """
    Returns a generator of all the markdown sources files.

    This includes converting notebooks to markdown so that the prose can be
    checked.
    """
    markdown_file_paths = (source_file_path,)

    for path in markdown_file_paths:
        yield path, path

    markdown_exporter = nbconvert.MarkdownExporter()
    notebook_directory = root / "assets/nbs"
    for path in notebook_directory.glob("**/*.ipynb"):
        if "checkpoint" not in str(path) and "submissions" not in str(path):
            md, _ = markdown_exporter.from_file(path)

            temporary_file = tempfile.NamedTemporaryFile(suffix=".md")
            temporary_file_path = pathlib.Path(temporary_file.name)

            temporary_file_path.write_text(md)
            yield path, temporary_file_path


def render_template(template_file, template_vars, searchpath="./templates/"):
    """
    Render a jinja2 template
    """
    templateLoader = jinja2.FileSystemLoader(searchpath=searchpath)
    template_env = jinja2.Environment(loader=templateLoader)
    template = template_env.get_template(template_file)
    return template.render(template_vars)


@task
def build(
    c,
    source_file_path=SOURCE_FILE_PATH,
    root=WEB_ROOT,
    title=TITLE,
    description=DESCRIPTION,
    keywords=KEYWORDS,
    author=AUTHOR,
):
    """
    Build the single page site.
    """
    md_string = source_file_path.read_text()
    content = markdown.markdown(md_string)
    html = render_template(
        "home.html",
        {
            "content": content,
            "root": root,
            "title": title,
            "description": description,
            "keywords": keywords,
            "author": author,
        },
    )
    out_dir = pathlib.Path("_build")
    out_dir.mkdir(exist_ok=True)
    (out_dir / "index.html").write_text(html)
    distutils.dir_util.copy_tree("assets", str(out_dir / "assets"))


@task
def spellcheck(c, root=REPO_ROOT):
    """
    Run the book through a spell checker.

    Known exceptions are in `known.py`
    """
    exit_code = 0

    for name, markdown_file_path in get_markdown_files_to_check():

        markdown = markdown_file_path.read_text()
        aspell_output = subprocess.check_output(
            ["aspell", "-t", "--list", "--lang=en_GB"], input=markdown, text=True
        )
        incorrect_words = set(aspell_output.split("\n")) - {""} - known.words
        if len(incorrect_words) > 0:
            print(f"In {name} the following words are not known: ")
            for string in sorted(incorrect_words):
                print(string)
            exit_code = 1

    sys.exit(exit_code)


@task
def prosecheck(c, root=REPO_ROOT):
    """
    Run the following checkers for prose on all markdown source files:

    - Proselint
    - Alex

    Proselint is used as a python library. Alex (an npm tool) is used by running
    the command line tool on the markdown file.

    Known exceptions are in `known.py`
    """
    exit_code = 0
    for name, markdown_file_path in get_markdown_files_to_check():
        markdown = markdown_file_path.read_text()
        relative_markdown_path = str(name.relative_to(root))
        exceptions = known.prose_exceptions.get(relative_markdown_path, set(()))

        for exception in exceptions:
            markdown = markdown.replace(exception, "")

        suggestions = proselint.tools.lint(markdown)
        ignored_suggestions = known.prose_suggestions_to_ignore.get(
            relative_markdown_path, set(())
        )
        for suggestion in filter(
            lambda suggestion: suggestion[0] not in ignored_suggestions, suggestions
        ):
            print(f"proselint suggests the following in {relative_markdown_path}")
            print(suggestion)
            exit_code = 1

        output = subprocess.run(
            ["alex", markdown_file_path], capture_output=True, check=False
        )

        if output.returncode > 0:
            exit_code = max(output.returncode, exit_code)
            stderr = output.stderr.decode("utf-8")
            print(stderr.replace(str(markdown_file_path), relative_markdown_path))

    sys.exit(exit_code)
