"use client";
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { Check, ChevronDown, Search, X } from "lucide-react";
import { COUNTRIES, searchCountries, type Country } from "@/lib/countries";

type CountrySelectProps = {
  defaultValue?: string; value?: string; onChange?: (value: string) => void;
  name?: string; label?: string; required?: boolean; disabled?: boolean;
  multiple?: boolean; maxLength?: number;
};

export default function CountrySelect({ defaultValue = "", value: controlledValue, onChange,
  name = "nationality", label = "Nationality / country or region", required = true,
  disabled = false, multiple = false, maxLength }: CountrySelectProps) {
  const id = useId();
  const [localValue, setLocalValue] = useState(defaultValue);
  const value = controlledValue ?? localValue;
  const selected = value ? (multiple ? value.split("; ") : [value]) : [];
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [invalid, setInvalid] = useState(false);
  const [limitError, setLimitError] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const search = useRef<HTMLInputElement>(null);
  // Keep historical values until explicitly replaced or removed. Typing into
  // search never changes the value submitted to the profile or planning API.
  const legacy: Country[] = selected.filter(name => !COUNTRIES.some(country => country.name === name))
    .map((name, index) => ({ code: `saved-${index}`, name, localName: "" }));
  const options = [...legacy.filter(country => !query || country.name.toLowerCase().includes(query.toLowerCase())), ...searchCountries(query)];
  const placeholder = multiple ? "Select one or more countries" : "Select a country or region";

  function update(next: string) {
    setLocalValue(next); onChange?.(next); setInvalid(false); setLimitError(false);
  }

  useEffect(() => {
    if (!open) return;
    search.current?.focus();
    function outside(event: PointerEvent) {
      if (event.target instanceof Node && !root.current?.contains(event.target)) setOpen(false);
    }
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);
  useEffect(() => {
    if (open) root.current?.querySelector('[data-active="true"]')?.scrollIntoView({ block: "nearest" });
  }, [open, active, query]);

  function show() {
    setQuery(""); setLimitError(false);
    const all = [...legacy, ...COUNTRIES];
    setActive(Math.max(0, all.findIndex(country => selected.includes(country.name))));
    setOpen(true);
  }
  function choose(country: Country) {
    const next = multiple
      ? (selected.includes(country.name) ? selected.filter(name => name !== country.name) : [...selected, country.name]).join("; ")
      : country.name;
    if (maxLength && next.length > maxLength) { setLimitError(true); return; }
    update(next);
    if (multiple) { setQuery(""); setActive(0); search.current?.focus(); }
    else { setOpen(false); setQuery(""); trigger.current?.focus(); }
  }
  function navigate(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (options.length) setActive(current => (current + (event.key === "ArrowDown" ? 1 : -1) + options.length) % options.length);
    } else if (event.key === "Enter") {
      event.preventDefault(); // Selecting/filtering must not submit the profile.
      if (options[active]) choose(options[active]);
    } else if (event.key === "Escape") {
      event.preventDefault(); setOpen(false); trigger.current?.focus();
    }
  }
  return <div className="country-field" ref={root} onBlur={event => {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOpen(false);
  }}>
    <label id={`${id}-label`} htmlFor={`${id}-trigger`}>{label}{required && name !== "nationality" ? " *" : ""}</label>
    <button type="button" className={`country-trigger ${value ? "" : "placeholder"}`} ref={trigger}
      id={`${id}-trigger`} aria-labelledby={`${id}-label ${id}-value`} aria-haspopup="dialog" aria-expanded={open}
      aria-controls={open ? `${id}-popup` : undefined} aria-invalid={invalid || undefined}
      aria-describedby={invalid ? `${id}-error` : undefined} disabled={disabled}
      onClick={() => open ? setOpen(false) : show()}
      onKeyDown={event => { if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); show(); } }}>
      <span id={`${id}-value`}>{selected.join(", ") || placeholder}</span><ChevronDown size={16} aria-hidden="true" />
    </button>
    <select className="country-form-value" name={name} value={value} required={required} disabled={disabled}
      tabIndex={-1} aria-hidden="true" onChange={event => update(event.target.value)}
      onInvalid={event => { event.preventDefault(); setInvalid(true); show(); }}>
      <option value="">{placeholder}</option>
      {multiple && selected.length > 1 && <option value={value}>{selected.join(", ")}</option>}
      {legacy.map(country => <option key={country.code} value={country.name}>{country.name}</option>)}
      {COUNTRIES.map(country => <option key={country.code} value={country.name}>{country.name}</option>)}
    </select>
    {multiple && selected.length > 0 && <div className="country-selections" aria-label="Selected destinations">
      {selected.map(country => <button type="button" key={country} disabled={disabled} aria-label={`Remove ${country}`}
        onClick={() => update(selected.filter(name => name !== country).join("; "))}>{country}<X size={12} aria-hidden="true" /></button>)}
    </div>}
    {invalid && <span id={`${id}-error`} className="country-error" role="alert">Select a country or region from the list.</span>}
    {open && <div className="country-popup" id={`${id}-popup`} role="dialog" aria-labelledby={`${id}-label`}>
      <div className="country-search"><Search size={16} aria-hidden="true" /><input ref={search} type="search"
        role="combobox" aria-label="Search countries or regions" aria-expanded={true} aria-controls={`${id}-list`}
        aria-autocomplete="list" aria-activedescendant={options[active] ? `${id}-${options[active].code}` : undefined}
        placeholder="Search by name or code…" autoComplete="off" value={query}
        onChange={event => { setQuery(event.target.value); setActive(0); }} onKeyDown={navigate} /></div>
      <div className="country-result-count" role="status">{options.length} {options.length === 1 ? "result" : "results"}</div>
      {limitError && <p className="country-error" role="alert">Too many destinations. Remove a country before adding another.</p>}
      <ul id={`${id}-list`} role="listbox" aria-label="Countries and regions" aria-multiselectable={multiple || undefined} className="country-options">
        {options.map((country, index) => <li key={country.code} id={`${id}-${country.code}`} role="option"
          aria-selected={selected.includes(country.name)} data-active={index === active} onPointerDown={event => event.preventDefault()}
          onPointerMove={() => setActive(index)} onClick={() => choose(country)}>
          <span>{country.name}{country.code.startsWith("saved-") && <small>Previously saved value</small>}</span>
          {selected.includes(country.name) && <Check size={15} aria-hidden="true" />}
        </li>)}
      </ul>
      {!options.length && <p className="country-empty">No matching country or region. Try another name or a two-letter code.</p>}
    </div>}
  </div>;
}
