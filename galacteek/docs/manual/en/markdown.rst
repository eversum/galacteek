.. _markdown:

Markdown
========

If you're new to Markdown, visit
`this page <ipfs://bafkreigbtkby5vpzwwpbqv7whr55hbp5s7bje5rrdxsv2rbarceauo773a/>`_
to learn the basics.

IPFS links
----------

In galacteek you can use specific Markdown syntax to
easily generate IPFS links. This can be used in the chat,
blog editor, when editing a Markdown file in the text editor ..

To generate a link to a :term:`CID` or a full
:term:`IPFS path`, use::

    @CID
    @fullpath

Examples::

    @bafybeiard2qjxagn77k7kouc5huyvei7hgrmoztpl2zswk25leh5zwd7za
    @bafybeiard2qjxagn77k7kouc5huyvei7hgrmoztpl2zswk25leh5zwd7za/test
    @/ipfs/bafybeiard2qjxagn77k7kouc5huyvei7hgrmoztpl2zswk25leh5zwd7za/test
    @/ipns/ipfs.io

You can also define a label name for the URLs::

    photos@bafybeiard2qjxagn77k7kouc5huyvei7hgrmoztpl2zswk25leh5zwd7za
    awesome@/ipns/awesome.ipfs.io

If you use multiple **@**, it will generate gatewayed links as well::

    awesome@@/ipns/docs.ipfs.io
    more@@@bafybeiard2qjxagn77k7kouc5huyvei7hgrmoztpl2zswk25leh5zwd7za

Images and videos
-----------------

Embed an image using this syntax (using an exclamation mark **!**
at the beginning)::

    !@bafkreiaophpetg3yoq6r5eu2lx2etl4neur2e5wh3yiknep55lukupo2t4
    bigcat!@bafkreiaophpetg3yoq6r5eu2lx2etl4neur2e5wh3yiknep55lukupo2t4

Embed a video stored on IPFS using this syntax (using a **%**
at the beginning)::

    %@bafybeibdtp3sm62jk62s3o352ecjeqvymrmuqluopeeppwiggm7bx64kgy

Extensions
----------

Common Markdown is supported, with the following extensions:

- attrlist_: this adds a syntax to define attributes on the various
  HTML elements in markdown’s output.
- mdxunimoji_: Converts defined emoticon symbols to Unicode emojis

.. _attrlist: https://python-markdown.github.io/extensions/attr_list/
.. _mdxunimoji: https://github.com/kernc/mdx_unimoji
