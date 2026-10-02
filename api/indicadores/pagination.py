from rest_framework.pagination import PageNumberPagination


class Paginacao(PageNumberPagination):
    """100 itens por página por padrão; o cliente pode pedir até 1000 com `page_size`."""

    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 1000
