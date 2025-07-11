import type { Meta, StoryObj } from '@storybook/react';
import { useState } from 'react';
import { AirportAutocomplete } from './AirportAutocomplete';
import type { Airport } from './types';

const meta = {
  title: 'Components/AirportAutocomplete',
  component: AirportAutocomplete,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
  argTypes: {
    value: {
      control: 'text',
      description: 'Current value of the input',
    },
    placeholder: {
      control: 'text',
      description: 'Placeholder text for the input',
    },
    disabled: {
      control: 'boolean',
      description: 'Whether the input is disabled',
    },
    required: {
      control: 'boolean',
      description: 'Whether the input is required',
    },
    className: {
      control: 'text',
      description: 'Additional CSS classes',
    },
  },
} satisfies Meta<typeof AirportAutocomplete>;

export default meta;
type Story = StoryObj<typeof meta>;

interface ControlledProps {
  value?: string;
  onChange?: (code: string) => void;
  [key: string]: any;
}

// Helper component for controlled stories
const ControlledAirportAutocomplete = (props: ControlledProps) => {
  const [value, setValue] = useState(props.value || '');
  const [selectedAirport, setSelectedAirport] = useState<Airport | null>(null);

  return (
    <div className="w-96 space-y-4">
      <AirportAutocomplete
        {...props}
        value={value}
        onChange={setValue}
        onSelect={(airport) => {
          setSelectedAirport(airport);
          // Log selected airport for demo purposes
          // eslint-disable-next-line no-console
          console.log('Selected airport:', airport);
        }}
      />

      {selectedAirport && (
        <div className="p-4 bg-gray-100 dark:bg-gray-800 rounded-md">
          <h3 className="font-semibold mb-2">Selected Airport:</h3>
          <dl className="grid grid-cols-2 gap-2 text-sm">
            <dt className="font-medium">Code:</dt>
            <dd>{selectedAirport.iata || selectedAirport.icao}</dd>
            <dt className="font-medium">Name:</dt>
            <dd>{selectedAirport.name}</dd>
            <dt className="font-medium">Location:</dt>
            <dd>{selectedAirport.municipality}, {selectedAirport.country}</dd>
            <dt className="font-medium">Coordinates:</dt>
            <dd>{selectedAirport.lat.toFixed(4)}, {selectedAirport.lon.toFixed(4)}</dd>
          </dl>
        </div>
      )}
    </div>
  );
};

export const Default: Story = {
  render: (args) => <ControlledAirportAutocomplete {...args} />,
  args: {
    value: '',
    onChange: () => {},
    placeholder: 'Enter airport name or code',
  },
};

export const WithInitialValue: Story = {
  render: (args) => <ControlledAirportAutocomplete {...args} />,
  args: {
    value: 'BOS',
    placeholder: 'Enter airport name or code',
  },
};

export const Disabled: Story = {
  render: (args) => <ControlledAirportAutocomplete {...args} />,
  args: {
    value: 'LAX',
    disabled: true,
    placeholder: 'Enter airport name or code',
  },
};

export const Required: Story = {
  render: (args) => (
    <form onSubmit={(e) => { e.preventDefault(); alert('Form submitted!'); }}>
      <div className="space-y-4">
        <ControlledAirportAutocomplete {...args} />
        <button
          type="submit"
          className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
        >
          Submit
        </button>
      </div>
    </form>
  ),
  args: {
    value: '',
    onChange: () => {},
    required: true,
    placeholder: 'Select departure airport (required)',
  },
};

export const WithCustomStyling: Story = {
  render: (args) => <ControlledAirportAutocomplete {...args} />,
  args: {
    value: '',
    onChange: () => {},
    className: 'custom-airport-input',
    placeholder: 'Custom styled input',
  },
};

export const LoadingState: Story = {
  render: () => {
    // This would show the loading state briefly on initial load
    return (
      <div className="w-96">
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
          The component shows a loading state while initializing the airport data.
          Type to see the search in action.
        </p>
        <ControlledAirportAutocomplete placeholder="Type to search..." />
      </div>
    );
  },
  args: {
    value: '',
    onChange: () => {},
  },
};

const NoResultsStory = () => {
  const [value, setValue] = useState('xyz123');

  return (
    <div className="w-96">
      <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
        Example showing the &quot;No airports found&quot; message
      </p>
      <AirportAutocomplete
        value={value}
        onChange={setValue}
        placeholder="Try searching for something else"
      />
    </div>
  );
};

export const NoResults: Story = {
  render: NoResultsStory,
  args: {
    value: '',
    onChange: () => {},
  },
};

export const MobileView: Story = {
  parameters: {
    viewport: {
      defaultViewport: 'iphone12',
    },
  },
  render: (args) => (
    <div className="p-4">
      <ControlledAirportAutocomplete {...args} />
    </div>
  ),
  args: {
    value: '',
    onChange: () => {},
    placeholder: 'Enter airport',
  },
};

export const DarkMode: Story = {
  parameters: {
    backgrounds: {
      default: 'dark',
    },
  },
  render: (args) => (
    <div className="dark">
      <div className="p-8 bg-gray-900 rounded-lg">
        <ControlledAirportAutocomplete {...args} />
      </div>
    </div>
  ),
  args: {
    value: '',
    onChange: () => {},
    placeholder: 'Enter airport name or code',
  },
};

export const WithAccessibility: Story = {
  render: (args) => (
    <div className="w-96 space-y-2">
      <label htmlFor="departure-airport" className="block text-sm font-medium">
        Departure Airport
      </label>
      <ControlledAirportAutocomplete {...args} />
      <p id="airport-help" className="text-sm text-gray-600 dark:text-gray-400">
        Search by airport name, city, or IATA/ICAO code
      </p>
    </div>
  ),
  args: {
    value: '',
    onChange: () => {},
    id: 'departure-airport',
    'aria-describedby': 'airport-help',
    placeholder: 'e.g., JFK, Los Angeles, CDG',
  },
};

const MultipleInstancesStory = () => {
  const [departure, setDeparture] = useState('');
  const [arrival, setArrival] = useState('');

  return (
    <div className="w-96 space-y-6">
      <div>
        <label className="block text-sm font-medium mb-2">
          Departure Airport
        </label>
        <AirportAutocomplete
          value={departure}
          onChange={setDeparture}
          placeholder="From..."
        />
      </div>

      <div>
        <label className="block text-sm font-medium mb-2">
          Arrival Airport
        </label>
        <AirportAutocomplete
          value={arrival}
          onChange={setArrival}
          placeholder="To..."
        />
      </div>
    </div>
  );
};

export const MultipleInstances: Story = {
  render: MultipleInstancesStory,
  args: {
    value: '',
    onChange: () => {},
  },
};
