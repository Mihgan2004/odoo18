/** @odoo-module **/

import { Component } from "@odoo/owl";

export class PvzListItem extends Component {
    static template = "cdek_odooAPI2.PvzListItem"; // Ссылка на XML-шаблон компонента
    static props = {
        pvz: { type: Object, optional: false }, // Данные одного ПВЗ
        isSelected: { type: Boolean, optional: true, default: false },
        onPvzClicked: { type: Function, optional: false },
    };

    setup() {
        // Никакой сложной логики состояний здесь обычно не нужно,
        // компонент просто отображает props и вызывает callback.
    }

    get fullAddress() {
        // Пример формирования полного адреса, если нужно
        let address = this.props.pvz.address || "";
        if (this.props.pvz.address_full && this.props.pvz.address_full !== this.props.pvz.address) {
            address = this.props.pvz.address_full;
        }
        return address;
    }

    get paymentInfo() {
        const payments = [];
        if (this.props.pvz.is_cash_allowed) {
            payments.push(this.env._t("Cash"));
        }
        if (this.props.pvz.is_card_allowed) {
            payments.push(this.env._t("Card"));
        }
        return payments.join(", ");
    }

    onClick() {
        this.props.onPvzClicked({ detail: this.props.pvz });
    }
}