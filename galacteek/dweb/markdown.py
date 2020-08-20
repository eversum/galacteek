import markdown

from galacteek.dweb.pygmentedmarkdown import CodeBlockExtension


def markitdown(text):
    return markdown.markdown(
        text, extensions=[
            CodeBlockExtension(),
            'attr_list'
        ]
    )
