/** @odoo-module **/

import { Component } from "@odoo/owl";
import { PvzListItem } from "./pvz_list_item"; // Импортируем подкомпонент

export class PvzList extends Component {
    static template = "cdek_odooAPI2.PvzList";
    static components = { PvzListItem }; // Регистрируем подкомпонент
    static props = {
        pvzList: { type: Array, optional: false, default: [] },
        selectedPvzCode: { type: [String, Boolean], optional: true, default: false }, // Код выбранного ПВЗ
        onPvzSelected: { type: Function, optional: false }, // Callback при выборе ПВЗ из списка
    };

    setup() {
        // Никакой сложной логики состояния здесь обычно не требуется,
        // список и выбранный элемент передаются через props.
    }

    // Эта функция будет передана как callback в PvzListItem
    handlePvzClicked(pvzData) {
        this.props.onPvzSelected(pvzData); // Просто "пробрасываем" событие выше
    }
}