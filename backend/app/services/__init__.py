"""Service layer — business logic kept out of the routers.

Each service is a small, focused class/module that routers call into. Services
own all interaction with the database, parsers, AI client, and vector store.
"""
