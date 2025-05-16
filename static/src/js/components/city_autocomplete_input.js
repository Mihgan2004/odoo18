/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { debounce } from "@web/core/utils/timing";

export class CityAutocompleteInput extends Component {
    static template = "cdek_odooAPI2.CityAutocompleteInput";
    static props = {
        id: { type: String, optional: true },
        selectedCity: { type: Object, optional: true },
        onCitySelected: Function,
        placeholder: { type: String, optional: true },
    };

    setup() {
        this.rpc = useService("rpc");
        this.notification = useService("notification");

        this.state = useState({
            searchTerm: this.props.selectedCity ? this.props.selectedCity.city : "",
            suggestions: [],
            isLoading: false,
            showSuggestions: false,
        });

        this.debouncedSearch = debounce(this.searchCities, 300);

        onWillStart(() => {
            if (this.props.selectedCity && this.props.selectedCity.city) {
                 this.state.searchTerm = `${this.props.selectedCity.city}${this.props.selectedCity.region ? ', ' + this.props.selectedCity.region : ''}`;
            }
        });
    }

    onInput(ev) {
        this.state.searchTerm = ev.target.value;
        if (this.state.searchTerm.length > 1) {
            this.state.showSuggestions = true;
            this.debouncedSearch();
        } else {
            this.state.suggestions = [];
            this.state.showSuggestions = false;
        }
    }

    async searchCities() {
        if (this.state.searchTerm.length < 2) {
            this.state.suggestions = [];
            return;
        }
        this.state.isLoading = true;
        try {
            const result = await this.rpc("/cdek/city/search", {
                query: this.state.searchTerm,
                limit: 10,
            });
            if (result && !result.error) {
                this.state.suggestions = result;
            } else if (result && result.error) {
                 this.notification.add(result.message, { type: 'warning' });
                 this.state.suggestions = [];
            } else {
                this.state.suggestions = [];
            }
        } catch (err) {
            this.notification.add(this.env._t("Error searching cities."), { type: 'danger' });
            console.error("City search error:", err);
            this.state.suggestions = [];
        } finally {
            this.state.isLoading = false;
        }
    }

    selectSuggestion(city) {
        this.state.searchTerm = `${city.city}${city.region ? ', ' + city.region : ''}`;
        this.state.suggestions = [];
        this.state.showSuggestions = false;
        this.props.onCitySelected({ detail: city });
    }

    onFocus() {
        if (this.state.searchTerm.length > 1 && this.state.suggestions.length > 0) {
            this.state.showSuggestions = true;
        }
    }

    onBlur() {
        // Небольшая задержка, чтобы успел сработать клик по предложению
        setTimeout(() => {
            this.state.showSuggestions = false;
        }, 200);
    }
}