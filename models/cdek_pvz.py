# -*- coding: utf-8 -*-
from odoo import models, fields, api

class CdekPvz(models.Model):
    _name = 'cdek.pvz'
    _description = 'Пункт выдачи заказов СДЭК'
    _order = 'name'

    name = fields.Char(string='Наименование ПВЗ', required=True, index=True)
    code = fields.Char(string='Код ПВЗ', required=True, index=True) # Уникальный код ПВЗ от СДЭК
    city_code = fields.Integer(string='Код города СДЭК')
    city_name = fields.Char(string='Город')
    country_code = fields.Char(string='Код страны') # ISO код страны, например, RU

    address_full = fields.Text(string='Полный адрес')
    address_comment = fields.Text(string='Комментарий к адресу')
    work_time = fields.Char(string='Время работы')
    phone = fields.Char(string='Телефон')
    email = fields.Char(string='Email')
    note = fields.Text(string='Примечание')
    type = fields.Selection([
        ('PVZ', 'Пункт выдачи'),
        ('POSTAMAT', 'Постамат')
    ], string='Тип ПВЗ', default='PVZ')
    owner_code = fields.Char(string='Код владельца') 
    take_only = fields.Boolean(string='Только выдача')
    is_dressing_room = fields.Boolean(string='Есть примерочная')
    have_cashless = fields.Boolean(string='Есть безналичный расчет')
    allowed_cod = fields.Boolean(string='Разрешен наложенный платеж')
    
    # Координаты для карты
    longitude = fields.Float(string='Долгота', digits=(10, 7))
    latitude = fields.Float(string='Широта', digits=(10, 7))

    # Технические поля
    last_synced = fields.Datetime(string='Последняя синхронизация') #

    _sql_constraints = [
        ('code_uniq', 'unique (code)', 'Код ПВЗ должен быть уникальным!')
    ]

    def name_get(self):
        result = []
        for record in self:
            name = f"[{record.code}] {record.name} ({record.address_full or ''})"
            result.append((record.id, name))
        return result

    @api.model
    def find_or_create_pvz(self, pvz_data):
        """
        Ищет ПВЗ по коду или создает новый.
        pvz_data - словарь с данными от API СДЭК.
        """
        pvz = self.search([('code', '=', pvz_data.get('code'))], limit=1)
        if not pvz:
            # Адаптируйте ключи pvz_data под поля вашей модели
            vals = {
                'code': pvz_data.get('code'),
                'name': pvz_data.get('name'),
                'city_code': pvz_data.get('location', {}).get('city_code'),
                'city_name': pvz_data.get('location', {}).get('city'),
                'country_code': pvz_data.get('location', {}).get('country_code'),
                'address_full': pvz_data.get('location', {}).get('address_full') or pvz_data.get('location', {}).get('address'),
                'work_time': pvz_data.get('work_time'),
                'phone': ', '.join([p.get('number') for p in pvz_data.get('phones', []) if p.get('number')]),
                'email': pvz_data.get('email'),
                'note': pvz_data.get('note'),
                'type': pvz_data.get('type', 'PVZ').upper(), # У СДЭК может быть 'PVZ' или 'POSTAMAT'
                'longitude': pvz_data.get('location', {}).get('longitude'),
                'latitude': pvz_data.get('location', {}).get('latitude'),
                'is_dressing_room': any(s.get('type') == 'FITTING_ROOM' for s in pvz_data.get('services', [])), # Пример
                'have_cashless': any(s.get('type') == 'CARD' for s in pvz_data.get('services', [])), # Пример
                'allowed_cod': pvz_data.get('cash_on_delivery'), # Проверьте точное поле в API
                # Добавьте другие поля по необходимости
            }
            pvz = self.create(vals)
        else:

            pass
        return pvz.id