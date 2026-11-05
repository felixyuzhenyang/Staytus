"use client";
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { Check, ChevronDown, Search } from "lucide-react";
import { COUNTRIES, searchCountries, type Country } from "@/lib/countries";

export default function CountrySelect({ defaultValue = "", disabled = false }: { defaultValue?: string; disabled?: boolean }) {
  const id = useId();
  const [value, setValue] = useState(defaultValue);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [invalid, setInvalid] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const search = useRef<HTMLInputElement>(null);
  // Preserve historical free-text values until the user explicitly selects a
  // replacement. Search text is never the submitted nationality.
  const legacy: Country | null = defaultValue && !COUNTRIES.some(country => country.name === defaultValue)
    ? { code: "saved", name: defaultValue, localName: "" } : null;
  const options = [...(legacy && (!query || legacy.name.toLowerCase().includes(query.toLowerCase())) ? [legacy] : []), ...searchCountries(query)];

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
    setQuery("");
    const all = legacy ? [legacy, ...COUNTRIES] : COUNTRIES;
    setActive(Math.max(0, all.findIndex(country => country.name === value)));
    setOpen(true);
  }
  function choose(country: Country) {
    setValue(country.name); setInvalid(false); setOpen(false); setQuery("");
    trigger.current?.focus();
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
    <label id={`${id}-label`} htmlFor={`${id}-trigger`}>Nationality / country or region</label>
    <button type="button" className={`country-trigger ${value ? "" : "placeholder"}`} ref={trigger}
      id={`${id}-trigger`} aria-labelledby={`${id}-label ${id}-value`} aria-haspopup="dialog" aria-expanded={open}
      aria-controls={open ? `${id}-popup` : undefined} aria-invalid={invalid || undefined}
      aria-describedby={invalid ? `${id}-error` : undefined} disabled={disabled}
      onClick={() => open ? setOpen(false) : show()}
      onKeyDown={event => { if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); show(); } }}>
      <span id={`${id}-value`}>{value || "Select a country or region"}</span><ChevronDown size={16} aria-hidden="true" />
    </button>
    <select className="country-form-value" name="nationality" value={value} required disabled={disabled}
      tabIndex={-1} aria-hidden="true" onChange={event => setValue(event.target.value)}
      onInvalid={event => { event.preventDefault(); setInvalid(true); show(); }}>
      <option value="">Select a country or region</option>
      {legacy && <option value={legacy.name}>{legacy.name}</option>}
      {COUNTRIES.map(country => <option key={country.code} value={country.name}>{country.name}</option>)}
    </select>
    {invalid && <span id={`${id}-error`} className="country-error" role="alert">Select a country or region from the list.</span>}
    {open && <div className="country-popup" id={`${id}-popup`} role="dialog" aria-labelledby={`${id}-label`}>
      <div className="country-search"><Search size={16} aria-hidden="true" /><input ref={search} type="search"
        role="combobox" aria-label="Search countries or regions" aria-expanded={true} aria-controls={`${id}-list`}
        aria-autocomplete="list" aria-activedescendant={options[active] ? `${id}-${options[active].code}` : undefined}
        placeholder="Search by name or code…" autoComplete="off" value={query}
        onChange={event => { setQuery(event.target.value); setActive(0); }} onKeyDown={navigate} /></div>
      <div className="country-result-count" role="status">{options.length} {options.length === 1 ? "result" : "results"}</div>
      <ul id={`${id}-list`} role="listbox" aria-label="Countries and regions" className="country-options">
        {options.map((country, index) => <li key={country.code} id={`${id}-${country.code}`} role="option"
          aria-selected={country.name === value} data-active={index === active} onPointerDown={event => event.preventDefault()}
          onPointerMove={() => setActive(index)} onClick={() => choose(country)}>
          <span>{country.name}{country.code === "saved" && <small>Previously saved value</small>}</span>
          {country.name === value && <Check size={15} aria-hidden="true" />}
        </li>)}
      </ul>
      {!options.length && <p className="country-empty">No matching country or region. Try another name or a two-letter code.</p>}
    </div>}
  </div>;
}
