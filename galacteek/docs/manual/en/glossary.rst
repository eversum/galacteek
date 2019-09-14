.. _galacteek-glossary:


==========
 Glossary
==========


.. glossary::

    CID
        
        IPFS Content IDentifier.
        
        Identifies content in IPFS. There are two versions
        of identifiers: CIDv0 (in base58) and CIDv1 (can be represented
        in base58 or base32).
        
        CIDv0 examples (will always start with *Qm*)::

            QmZGqE15BKQqrm6ADmnRyBLQSF1Ht16T9GSmp88vFxZ1Nu
            QmUvdbNn65yvkxoGU3FBNbZWEpvR72LGiVAY15LYKRkY6k

        CIDv1 examples::

            zdj7WZ4rubKSt8YvKkLRg92HMU3X7HBhdM7p8azhuyTbe1zrG
            bafybeidhx5nzmk4n7vj24wjbyx5lcvrxjdrrt5gg7rejzydfixqlwx7ae4

    CIDv0

        IPFS Content IDentifier (version 0)

    CIDv1

        IPFS Content IDentifier (version 1)

    CID upgrade

        The process of converting/upgrading a :term:`CIDv0` (CID version 0)
        to a :term:`CIDv1` (CID version 1)

    DAG

        Directed Acyclic Graph. From Wikipedia::

            In mathematics and computer science, a directed acyclic graph
            (DAG /ˈdæɡ/), is a finite directed graph with no directed cycles. 

            DAGs can model many different kinds of information.

    dweb

        The distributed web

    galacteek

        Browser for the distributed web

    go-ipfs

        IPFS daemon implementation in Go

    DHT
    
        Distributed Hash Table

        From Wikipedia::

            A distributed hash table (DHT) is a class of a decentralized
            distributed system that provides a lookup service similar to a
            hash table: (key, value) pairs are stored in a DHT, and any
            participating node can efficiently retrieve the value associated
            with a given key

    IPFS

        InterPlanetary File System

        https://www.ipfs.io

        ipns://ipfs.io

    IPFS path

        An IPFS path is a full path to an IPFS object. Examples::

            /ipfs/bafybeid534xc5jnyi4vgndvw7ngq72q7iadkloqyb5anh34ia7z3k32tw4/galacteek.png
            /ipns/ipfs.io

        :term:`galacteek` uses full IPFS paths wherever possible to
        reference objects.

    js-ipfs

        IPFS implementation in Javascript

    Merkle tree

        In cryptography and computer science, a hash tree or Merkle tree is
        a tree in which every non-leaf node is labelled with the cryptographic
        hash of the labels or values (in case of leaves) of its child nodes.
        Hash trees allow efficient and secure verification of the contents of
        large data structures. Hash trees are a generalization of hash lists
        and hash chains.

    MFS

        Mutable filesystem

        The Mutable Filesystem is an IPFS feature that gives the
        ability to manipulate IPFS objects as if they were part
        of a unix filesystem . This is used by the filemanager.
