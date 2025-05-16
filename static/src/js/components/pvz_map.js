/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useEffect, useRef, useState } from "@odoo/owl";
import { loadJS } from "@web/core/assets";
import { _t } from "@web/core/l10n/translation"; // Для перевода строк

// URL API Яндекс.Карт. Ключ будет подставлен из props.
const YANDEX_MAPS_API_URL_TEMPLATE = "https://api-maps.yandex.ru/2.1/?apikey={apikey}&lang=ru_RU&coordorder=latlong";

export class PvzMap extends Component {
    static template = "cdek_odooAPI2.PvzMap"; // Ссылка на XML-шаблон (мы его создали ранее)
    static props = {
        yandexApiKey: { type: String, optional: false },
        city: { type: Object, optional: true },      // { code, city, region, country_code, country, lat, lon }
        pvzList: { type: Array, optional: false, default: () => [] },
        selectedPvz: { type: Object, optional: true }, // Выбранный ПВЗ для выделения/центрирования
        onMapReady: { type: Function, optional: true },
        onPvzSelectedFromMap: { type: Function, optional: true },
        // Дополнительные props для управления картой, если нужно
        initialZoom: { type: Number, default: 12 },
        pvzMarkerPreset: { type: String, default: "islands#blueRapidTransitIcon" }, // Или 'islands#blueDotIcon' / 'islands#blueDeliveryIcon'
        selectedPvzMarkerPreset: { type: String, default: "islands#greenRapidTransitIcon" },
    };

    setup() {
        this.mapContainerRef = useRef("mapContainer"); // Ссылка на div-контейнер карты
        this.yandexMap = null;        // Инстанс карты Яндекса (window.ymaps.Map)
        this.placemarkManager = null; // Менеджер объектов для меток (window.ymaps.ObjectManager или GeoObjectCollection)
        this.isApiLoading = false;    // Флаг, что API карт в процессе загрузки

        this.state = useState({
            mapInitialized: false,
            mapLoadingError: null, // Сообщение об ошибке загрузки карты
            currentCityProcessedForBounds: null, // Для отслеживания, когда нужно пересчитывать границы
        });

        // Загрузка API и инициализация карты при монтировании компонента
        onMounted(async () => {
            await this._loadAndInitMap();
        });

        // Обновление маркеров при изменении списка ПВЗ или выбранного ПВЗ
        useEffect(
            () => {
                if (this.state.mapInitialized) {
                    this._updatePlacemarks();
                }
            },
            () => [this.props.pvzList, this.props.selectedPvz, this.state.mapInitialized]
        );

        // Перецентрирование карты при смене города или при первой загрузке с городом
        useEffect(
            () => {
                if (this.state.mapInitialized && this.props.city) {
                    // Если список ПВЗ пуст, центрируемся на городе.
                    // Если ПВЗ есть, _updatePlacemarks позаботится о границах.
                    if (!this.props.pvzList || this.props.pvzList.length === 0) {
                        this._recenterMapOnCity();
                    }
                }
            },
            () => [this.props.city, this.state.mapInitialized, this.props.pvzList]
        );

        // Очистка ресурсов карты при размонтировании компонента
        onWillUnmount(() => {
            if (this.yandexMap) {
                this.yandexMap.destroy();
                this.yandexMap = null;
                this.placemarkManager = null;
            }
        });
    }

    async _loadAndInitMap() {
        if (this.isApiLoading || this.state.mapInitialized) return;

        if (!this.props.yandexApiKey) {
            console.error("Yandex Maps API key is missing for PvzMap component.");
            this.state.mapLoadingError = _t("Yandex Maps API key is missing.");
            return;
        }

        this.isApiLoading = true;
        const apiUrl = YANDEX_MAPS_API_URL_TEMPLATE.replace("{apikey}", this.props.yandexApiKey);

        try {
            if (!window.ymaps) {
                await loadJS(apiUrl);
            }
            // ymaps.ready() гарантирует, что DOM и API карт готовы.
            await window.ymaps.ready();
            this._initMapInstance();

        } catch (error) {
            console.error("Failed to load or initialize Yandex Maps API:", error);
            this.state.mapLoadingError = _t("Failed to load Yandex Maps API. Please check your internet connection or API key.");
        } finally {
            this.isApiLoading = false;
        }
    }

    _initMapInstance() {
        if (!this.mapContainerRef.el || this.yandexMap) { // Если нет контейнера или карта уже инициализирована
            return;
        }

        const initialCoords = this._getInitialMapCenter();

        try {
            this.yandexMap = new window.ymaps.Map(this.mapContainerRef.el, {
                center: initialCoords,
                zoom: this.props.initialZoom,
                controls: ['zoomControl', 'fullscreenControl', 'typeSelector', 'rulerControl'] // Добавлены стандартные контролы
            });

            // Используем ObjectManager для более эффективной работы с большим количеством меток
            this.placemarkManager = new window.ymaps.ObjectManager({
                clusterize: true, // Включаем кластеризацию меток
                gridSize: 64,    // Размер ячейки кластеризатора
                clusterDisableClickZoom: true, // Отключаем авто-зум при клике на кластер (можно кастомизировать балун кластера)
                // Стили для кластеров (можно кастомизировать)
                clusterIconLayout: 'default#pieChart',
                clusterIconPieChartRadius: 15,
                clusterIconPieChartCoreRadius: 8,
                clusterIconPieChartStrokeWidth: 2,
            });

            this.yandexMap.geoObjects.add(this.placemarkManager);

            // Обработчик клика по метке в ObjectManager
            this.placemarkManager.objects.events.add('click', (e) => {
                const objectId = e.get('objectId');
                const clickedObject = this.placemarkManager.objects.getById(objectId);
                if (clickedObject && clickedObject.properties && clickedObject.properties.pvzData) {
                    if (this.props.onPvzSelectedFromMap) {
                        this.props.onPvzSelectedFromMap({ detail: clickedObject.properties.pvzData });
                    }
                }
            });

            // Обработчик открытия балуна на метке
            this.placemarkManager.objects.events.add('balloonopen', (e) => {
                 const objectId = e.get('objectId');
                 const obj = this.placemarkManager.objects.getById(objectId);
                 // Можно добавить кнопку "Выбрать" в балун и обработать ее здесь
                 // Пример: ymaps.jQuery(obj.getBalloon().getContentElement()).find('.select-pvz-btn') ...
            });


            this.state.mapInitialized = true;
            this.state.mapLoadingError = null; // Сбрасываем ошибку, если была
            if (this.props.onMapReady) {
                this.props.onMapReady();
            }
            // Сразу обновляем метки, если pvzList уже передан
            this._updatePlacemarks();

        } catch (error) {
            console.error("Error initializing Yandex Map instance:", error);
            this.state.mapLoadingError = _t("Error initializing map.");
            this.state.mapInitialized = false;
        }
    }

    _getInitialMapCenter() {
        if (this.props.city && this.props.city.lat && this.props.city.lon) {
            return [parseFloat(this.props.city.lat), parseFloat(this.props.city.lon)];
        }
        // Координаты по умолчанию (например, центр страны или крупного города)
        return [55.751244, 37.618423]; // Москва
    }

    _recenterMapOnCity() {
        if (this.yandexMap && this.props.city && this.props.city.lat && this.props.city.lon) {
            const newCenter = [parseFloat(this.props.city.lat), parseFloat(this.props.city.lon)];
            this.yandexMap.setCenter(newCenter, this.props.initialZoom).catch(err => console.warn("Map setCenter error:", err));
        }
    }

    _updatePlacemarks() {
        if (!this.yandexMap || !this.placemarkManager || !this.state.mapInitialized) {
            return;
        }

        const features = this.props.pvzList.map((pvz, index) => {
            if (!pvz.lat || !pvz.lon) return null;

            const isSelected = this.props.selectedPvz && pvz.code === this.props.selectedPvz.code;
            const balloonContent = `
                <div class="cdek-map-balloon">
                    <h6>${pvz.name || _t('Pickup Point')}</h6>
                    <p><small>${pvz.address_full || pvz.address || ''}</small></p>
                    ${pvz.work_time ? `<p><small><strong>${_t('Work Time')}:</strong> ${pvz.work_time}</small></p>` : ''}
                    ${pvz.phone ? `<p><small><strong>${_t('Phone')}:</strong> ${pvz.phone}</small></p>` : ''}
                    <button class="btn btn-primary btn-sm mt-1 cdek-select-on-map-btn" data-pvz-code="${pvz.code}">${_t('Select')}</button>
                </div>
            `;
            // Обработка кнопки "Выбрать" в балуне сложнее, так как она в DOM балуна, а не OWL.
            // Проще всего, если клик по самой метке уже выбирает ПВЗ.

            return {
                type: 'Feature',
                id: pvz.code || index, // Уникальный ID для метки
                geometry: {
                    type: 'Point',
                    coordinates: [parseFloat(pvz.lat), parseFloat(pvz.lon)]
                },
                properties: {
                    hintContent: pvz.name || _t('Pickup Point'),
                    balloonContentBody: balloonContent, // Основное содержимое балуна
                    // Дополнительные данные, которые могут понадобиться
                    pvzData: pvz, // Передаем весь объект ПВЗ
                },
                options: {
                    preset: isSelected ? this.props.selectedPvzMarkerPreset : this.props.pvzMarkerPreset,
                    // Пример кастомной иконки
                    // iconLayout: 'default#image',
                    // iconImageHref: `/your_module/static/src/img/${isSelected ? 'selected_marker.png' : 'marker.png'}`,
                    // iconImageSize: [30, 42],
                    // iconImageOffset: [-15, -42]
                }
            };
        }).filter(feature => feature !== null); // Удаляем ПВЗ без координат

        this.placemarkManager.removeAll(); // Очищаем предыдущие метки
        if (features.length > 0) {
            this.placemarkManager.add({
                type: 'FeatureCollection',
                features: features
            });

            // Автоматическое масштабирование карты, чтобы все метки были видны
            // Делаем это только если город не менялся, чтобы избежать конфликта с центрированием на город
            if (this.props.city && this.state.currentCityProcessedForBounds === this.props.city.code) {
                if (features.length === 1 && this.props.selectedPvz) {
                    // Если выбрана одна точка, центрируемся на ней с хорошим зумом
                     this.yandexMap.setCenter(
                        [parseFloat(this.props.selectedPvz.lat), parseFloat(this.props.selectedPvz.lon)],
                        15 // Более детальный зум для одной точки
                     ).catch(err => console.warn("Map setCenter (single point) error:", err));
                } else if (features.length > 0) {
                     this.yandexMap.setBounds(this.placemarkManager.getBounds(), {
                        checkZoomRange: true, // Проверять, чтобы зум не выходил за пределы min/maxZoom
                        zoomMargin: 35        // Отступы от границ карты
                    }).catch(err => console.warn("Map setBounds error:", err));
                }
            } else if (this.props.city) {
                // Если город изменился, сначала центрируемся на нем
                this._recenterMapOnCity();
                this.state.currentCityProcessedForBounds = this.props.city.code;
                 // После центрирования на городе, если есть точки, можно попробовать установить границы
                 if (features.length > 0) {
                    // Небольшая задержка, чтобы карта успела отцентрироваться
                    setTimeout(() => {
                         if (this.yandexMap && this.placemarkManager.getBounds()) {
                            this.yandexMap.setBounds(this.placemarkManager.getBounds(), {
                                checkZoomRange: true,
                                zoomMargin: 35
                            }).catch(err => console.warn("Map setBounds (after city change) error:", err));
                        }
                    }, 300);
                 }
            }

        } else if (this.props.city) {
            // Если ПВЗ нет, но город выбран, центрируемся на городе
            this._recenterMapOnCity();
            this.state.currentCityProcessedForBounds = this.props.city.code;
        }
    }
}