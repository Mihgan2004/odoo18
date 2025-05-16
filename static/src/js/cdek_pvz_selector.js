/** @odoo-module **/

import { Component, useState, onWillStart, onMounted, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { CityAutocompleteInput } from "./components/city_autocomplete_input";
import { PvzList } from "./components/pvz_list";
import { PvzMap } from "./components/pvz_map"; // Предполагается, что PvzMap будет реализован

export class CdekPvzSelector extends Component {
    static template = "cdek_odooAPI2.CdekPvzSelector"; // Ссылка на XML-шаблон компонента
    static components = { CityAutocompleteInput, PvzList, PvzMap };

    setup() {
        this.rpc = useService("rpc");
        this.notification = useService("notification"); // Для отображения уведомлений

        this.state = useState({
            orderId: this.props.orderId,
            carrierId: this.props.carrierId,
            selectedCity: null, // { code: '123', city: 'Москва', ... }
            availablePvz: [], // Список ПВЗ от API
            selectedPvz: null, // { code: 'PVZ_MSK1', name: '...', address: '...' }
            isLoadingCities: false,
            isLoadingPvz: false,
            filterText: "", // Для фильтрации списка ПВЗ
            yandexApiKey: null, // Для карты
            mapInitialized: false,
            currentPvzCode: this.props.currentPvzCode, // Код ПВЗ, сохраненный в заказе
        });

        this.pvzMapRef = useRef("pvzMapRef"); // Для доступа к компоненту карты

        onWillStart(async () => {
            // Загрузка ключа Яндекс.Карт (если используется)
            try {
                const key = await this.rpc("/cdek/config/yandex_key");
                if (key && !key.error) {
                    this.state.yandexApiKey = key;
                } else if (key && key.error) {
                    console.warn("CDEK: Could not fetch Yandex Maps API key:", key.message);
                }
            } catch (error) {
                console.error("CDEK: Error fetching Yandex Maps API key:", error);
            }

            // Если город уже есть у партнера доставки и есть код ПВЗ, пытаемся его предзаполнить
            if (this.props.partnerShippingCity && this.state.currentPvzCode) {
                // Упрощенный вариант: если есть код ПВЗ, то город уже должен быть корректным.
                // В идеале, нужно загрузить объект города по умолчанию, если он есть в адресе доставки
                // и потом загрузить ПВЗ для этого города.
                // Здесь мы можем сразу попробовать загрузить детали выбранного ПВЗ и отобразить его.
                // Но сначала нам нужен город для поиска других ПВЗ.
                const initialCityName = this.props.partnerShippingCity;
                if(initialCityName){
                    await this.fetchInitialCityAndPvz(initialCityName, this.state.currentPvzCode);
                }
            }
        });

        onMounted(() => {
            // Логика после монтирования компонента, например, инициализация карты, если она не является отдельным компонентом
            // Если PvzMap - это компонент, он сам позаботится о своей инициализации
        });
    }

    async fetchInitialCityAndPvz(cityName, pvzCode) {
        this.state.isLoadingCities = true;
        try {
            const cities = await this.rpc("/cdek/city/search", { query: cityName, limit: 1 });
            if (cities && cities.length > 0 && !cities.error) {
                this.state.selectedCity = cities[0]; // Предполагаем, что первый результат - верный
                await this.onCitySelected({ detail: cities[0] }, pvzCode); // Загружаем ПВЗ и пытаемся найти текущий
            } else if (cities && cities.error) {
                this.notification.add(cities.message, { type: 'danger' });
            }
        } catch (error) {
            this.notification.add(this.env._t("Error searching for initial city."), { type: 'danger' });
            console.error("CDEK City Search Error:", error);
        } finally {
            this.state.isLoadingCities = false;
        }
    }


    async onCitySelected(ev, preselectPvzCode = null) {
        const city = ev.detail;
        this.state.selectedCity = city;
        this.state.availablePvz = [];
        this.state.selectedPvz = null;
        this.state.filterText = "";

        if (!city || !city.code) return;

        this.state.isLoadingPvz = true;
        try {
            const pvzList = await this.rpc("/cdek/pvz/search", {
                city_code: city.code,
                // delivery_type: "PVZ", // Можно добавить фильтр по типу, если нужно
            });

            if (pvzList && !pvzList.error) {
                this.state.availablePvz = pvzList;
                if (preselectPvzCode) {
                    const foundPvz = pvzList.find(p => p.code === preselectPvzCode);
                    if (foundPvz) {
                        this.state.selectedPvz = foundPvz;
                        // Возможно, стоит обновить карту здесь, если она уже инициализирована
                         if (this.pvzMapRef.el && this.state.mapInitialized) {
                            // this.pvzMapRef.componentInstance.selectPvzOnMap(foundPvz); // Пример
                        }
                    }
                }
            } else if (pvzList && pvzList.error) {
                this.notification.add(pvzList.message, { type: 'danger' });
                this.state.availablePvz = [];
            } else {
                this.state.availablePvz = [];
            }
        } catch (error) {
            this.notification.add(this.env._t("Error fetching pickup points."), { type: 'danger' });
            console.error("CDEK PVZ Search Error:", error);
            this.state.availablePvz = [];
        } finally {
            this.state.isLoadingPvz = false;
        }
    }

    async onPvzSelected(ev) {
        const pvz = ev.detail;
        this.state.selectedPvz = pvz;
        // Обновить карту, если есть
        if (this.pvzMapRef.el && this.state.mapInitialized) {
            // this.pvzMapRef.componentInstance.selectPvzOnMap(pvz); // Пример вызова метода у дочернего компонента
        }

        // Сохранить выбор в заказе
        if (this.state.orderId && this.state.carrierId && this.state.selectedCity && pvz) {
            try {
                const result = await this.rpc("/shop/cdek/update_delivery", {
                    order_id: this.state.orderId,
                    carrier_id: this.state.carrierId,
                    delivery_type: 'pvz', // или pvz.type, если он есть
                    cdek_city_code: this.state.selectedCity.code,
                    cdek_city_name: this.state.selectedCity.city,
                    cdek_pvz_code: pvz.code,
                    cdek_pvz_address: pvz.address_full || pvz.address,
                });
                if (result && result.success) {
                    this.notification.add(this.env._t("Pickup point selected and order updated."), { type: 'success' });
                    // Odoo обычно сам перезагружает секцию заказа (order_details)
                    // Если этого не происходит, может потребоваться триггер:
                    // window.location.reload(); // Грубый вариант
                    // или более тонкий через Odoo JS API для обновления частей страницы
                    // publicWidget.trigger_up('widgets_start_request', {editableMode: false}); // может помочь
                } else if (result && result.error) {
                    this.notification.add(result.message || this.env._t("Failed to update order."), { type: 'danger' });
                }
            } catch (error) {
                this.notification.add(this.env._t("Error saving selection."), { type: 'danger' });
                console.error("CDEK Save Selection Error:", error);
            }
        }
    }

    onFilterInput(ev) {
        this.state.filterText = ev.target.value;
    }

    get filteredPvzList() {
        if (!this.state.filterText) {
            return this.state.availablePvz;
        }
        const lowerFilter = this.state.filterText.toLowerCase();
        return this.state.availablePvz.filter(pvz =>
            (pvz.name && pvz.name.toLowerCase().includes(lowerFilter)) ||
            (pvz.address && pvz.address.toLowerCase().includes(lowerFilter)) ||
            (pvz.code && pvz.code.toLowerCase().includes(lowerFilter))
        );
    }

    // Для карты
    onMapReady() {
        this.state.mapInitialized = true;
        // Если ПВЗ уже выбраны, можно отобразить их на карте
        if (this.state.availablePvz.length > 0) {
            // this.pvzMapRef.componentInstance.setPvzMarkers(this.state.availablePvz);
        }
    }
}