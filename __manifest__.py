# -*- coding: utf-8 -*-
{
    'name': 'CDEK API v2 Integration (cdek_odooAPI2)',
    'version': '18.0.1.0.0',
    'summary': 'Интеграция с CDEK API v2: модели, контроллеры, сервис и frontend‑виджет выбора ПВЗ',
    'description': """
Модуль интеграции Odoo с CDEK API v2.

Функционал:
- Расчёт стоимости и сроков доставки СДЭК.
- Frontend-виджет для выбора города и пункта выдачи заказов (ПВЗ) на странице оформления заказа.
- Отображение ПВЗ на карте (Яндекс.Карты или Google Maps).
- Сохранение выбранного ПВЗ в заказе клиента.
- Создание заказов в системе СДЭК.
- Получение печатных форм (этикеток) от СДЭК.
- Отслеживание статусов доставки СДЭК.
- Модели для хранения информации о ПВЗ и тарифах СДЭК.
- Сервис для инкапсуляции всех HTTP-запросов к CDEK API v2.
- Настройки модуля для управления API-ключами и параметрами по умолчанию.
    """,
    'category': 'Warehouse/Delivery', 
    'author': 'Your Company Name',
    'website': 'https://your.website.com', 
    'license': 'LGPL-3', 
    'depends': [
        'base',
        'sale',              
        'stock',              
        'delivery',       
        'website',            
        'website_sale',
    ],

    'data': [
        'security/ir.model.access.csv',

        'data/cdek_scheduled_actions.xml',

        'views/res_config_settings_views.xml',
        'views/delivery_carrier_views.xml',
        'views/stock_picking_views.xml',
        'views/sale_order_views.xml',
        'views/cdek_pvz_views.xml',
        'views/cdek_pvz_views.xml', 
        'views/cdek_tariff_views.xml',
        'views/cdek_menus.xml',

        'views/website_sale_delivery_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'cdek_odooAPI2/static/src/scss/cdek_widget.scss',

            'cdek_odooAPI2/static/src/js/cdek_pvz_selector.js',
            'cdek_odooAPI2/static/src/xml/cdek_pvz_selector.xml',

            'cdek_odooAPI2/static/src/js/components/city_autocomplete_input.js',

            'cdek_odooAPI2/static/src/js/components/pvz_list_item.js',

            'cdek_odooAPI2/static/src/js/components/pvz_list.js',

            'cdek_odooAPI2/static/src/js/components/pvz_map.js',
            'cdek_odooAPI2/static/src/js/cdek_pvz_selector_widget.js',

        ],

        'web.assets_tests': [ 
            'cdek_odooAPI2/static/tests/tours/cdek_checkout_tour.js', 
        ],
    },
    'installable': True,
    'application': True, 
    'auto_install': False,
}