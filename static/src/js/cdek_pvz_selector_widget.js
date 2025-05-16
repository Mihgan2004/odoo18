/** @odoo-module **/

import { registry } from "@web/core/registry";
import { mount } from "@odoo/owl";
import { CdekPvzSelector } from "./cdek_pvz_selector";

// Регистрируем виджет в категории public_widgets
registry.category("public_widgets").add("CdekPvzSelectorWidget", {
    // Селектор контейнера, в который виджет автоматически подмонтируется
    selector: "#cdekPvzSelectorRootContainer",

    /**
     * @override
     */
    async start() {
        // Считываем пропсы из data-атрибутов контейнера
        const orderId = this.el.dataset.orderId ? parseInt(this.el.dataset.orderId, 10) : null;
        const carrierId = this.el.datasetCarrierId ? parseInt(this.el.datasetCarrierId, 10) : null;
        const partnerShippingId = this.el.dataset.partnerShippingId
            ? parseInt(this.el.dataset.partnerShippingId, 10)
            : null;
        const partnerShippingCity = this.el.dataset.partnerShippingCity || "";

        // Если контейнер найден и это СДЭК
        if (!this.el || carrierId === null) {
            console.warn("CDEK Widget: невозможно инициализировать — нет carrierId или контейнера");
            return;
        }

        // Монтируем OWL-компонент
        mount(CdekPvzSelector, {
            target: this.el,
            props: {
                orderId,
                carrierId,
                partnerShippingId,
                partnerShippingCity,
            },
        });
    },
});
